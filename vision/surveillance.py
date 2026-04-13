"""
Background surveillance: fetch camera snapshots every N seconds (from Home Assistant),
run vision analysis, and save annotated images to the notify folder when anything is detected.
Posts detection notifications to the main API for DB storage.
Self-contained; no dependency on app.
"""
import asyncio
from datetime import datetime
from pathlib import Path
import json

import aiohttp
import asyncpg
import cv2
import numpy as np
import config



def _decode_image(image_bytes: bytes) -> np.ndarray | None:
    """Decode JPEG/PNG bytes from camera API to OpenCV image."""
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    return img


def _camera_entity_to_location(camera_entity: str) -> str:
    """Convert camera.frontdoor -> 'front door', camera.garage -> 'garage'."""
    part = camera_entity.split(".")[-1] if "." in camera_entity else camera_entity
    return part.replace("_", " ")


def _format_detection_message(detections: list, camera_entity: str) -> str:
    """Format detection labels into a message like 'John is detected at front door'."""
    location = _camera_entity_to_location(camera_entity)
    parts = []
    for d in detections:
        label = d.get("label", "")
        if label.startswith("RESIDENT:"):
            name = label.replace("RESIDENT:", "").strip().title()
            parts.append(f"{name} is detected at {location}")
        elif label == "KID":
            parts.append(f"Kid is detected at {location}")
        elif label == "DELIVERY":
            parts.append(f"Delivery person detected at {location}")
        else:
            parts.append(f"Stranger detected at {location}")
    return ". ".join(parts) if parts else f"Person detected at {location}"


async def _create_detection_notification_db(
    camera_entity: str,
    image_path: str,
    message: str,
) -> int | None:
    """
    Create a detection notification directly in Postgres and return its ID.
    This bypasses the main API HTTP endpoint.
    """
    if not config.VISION_DATABASE_URL:
        print("[surveillance] VISION_DATABASE_URL is not set; cannot create notifications")
        return None

    try:
        conn = await asyncpg.connect(config.VISION_DATABASE_URL)
    except Exception as e:
        print(f"[surveillance] Failed to connect to DB for notification insert: {e!r}")
        return None

    try:
        row = await conn.fetchrow(
            """
            INSERT INTO detection_notifications (message, camera_entity, image_path, is_read)
            VALUES ($1, $2, $3, $4)
            RETURNING id
            """,
            message,
            camera_entity,
            image_path,
            False,
        )
        if row:
            return int(row["id"])
        return None
    except Exception as e:
        print(f"[surveillance] Failed to insert detection notification: {e!r}")
        return None
    finally:
        await conn.close()


async def _update_detection_notification_db(
    notification_id: int,
    image_path: str,
    message: str,
) -> None:
    """
    Update an existing detection notification (image/message) directly in Postgres.
    """
    if not config.VISION_DATABASE_URL:
        print("[surveillance] VISION_DATABASE_URL is not set; cannot update notifications")
        return

    try:
        conn = await asyncpg.connect(config.VISION_DATABASE_URL)
    except Exception as e:
        print(f"[surveillance] Failed to connect to DB for notification update: {e!r}")
        return

    try:
        await conn.execute(
            """
            UPDATE detection_notifications
            SET message = $1, image_path = $2
            WHERE id = $3
            """,
            message,
            image_path,
            notification_id,
        )
    except Exception as e:
        print(f"[surveillance] Failed to update detection notification {notification_id}: {e!r}")
    finally:
        await conn.close()


async def _fetch_camera_entities_from_db() -> list[str] | None:
    """
    Fetch the list of camera entity IDs directly from the Postgres DB
    by reading the `configurations` table (key = 'tracked_cameras').
    """
    if not config.VISION_DATABASE_URL:
        print("[surveillance] VISION_DATABASE_URL is not set; cannot load cameras from DB")
        return None

    try:
        print(f"[surveillance] Connecting to DB at {config.VISION_DATABASE_URL!r} to load cameras")
        conn = await asyncpg.connect(config.VISION_DATABASE_URL)
    except Exception as e:
        print(f"[surveillance] Failed to connect to DB: {e!r}")
        return None

    try:
        row = await conn.fetchrow(
            "SELECT value FROM configurations WHERE key = $1 ORDER BY id DESC LIMIT 1",
            "tracked_cameras",
        )
        if not row:
            print("[surveillance] No 'tracked_cameras' configuration row found; returning empty list")
            return []
        value = row["value"]
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except Exception as e:
                print(f"[surveillance] Failed to json.loads config value string: {e!r}")
                return None
        if not isinstance(value, dict):
            print(f"[surveillance] Unexpected config value type after normalization: {type(value)!r}")
            return None
        entity_ids = value.get("entity_ids")
        if not isinstance(entity_ids, list):
            print("[surveillance] 'entity_ids' missing or not a list; returning empty list")
            return []
        print(f"[surveillance] Loaded camera entity_ids from DB: {entity_ids}")
        return [str(e) for e in entity_ids if isinstance(e, str)]
    except Exception as e:
        print(f"[surveillance] Error while fetching cameras from DB: {e!r}")
        return None
    finally:
        await conn.close()


async def _fetch_camera_entities(session: aiohttp.ClientSession) -> list[str] | None:
    """
    Fetch the list of camera entity IDs, preferring direct DB access.
    """
    print("[surveillance] Refreshing camera entities from DB...")
    db_entities = await _fetch_camera_entities_from_db()
    if db_entities is not None:
        print(f"[surveillance] Using camera entities from DB: {db_entities}")
        return db_entities
    print("[surveillance] DB camera fetch returned None; keeping existing camera list")
    return None


async def _fetch_snapshot(session: aiohttp.ClientSession, camera_entity: str) -> bytes | None:
    """Fetch a single camera snapshot from Home Assistant."""
    ha_url = config.HOME_ASSISTANT_URL
    print(f"[surveillance] Home Assistant URL (raw): {ha_url!r}")
    if not ha_url:
        print("[surveillance] HOME_ASSISTANT_URL is not set; cannot fetch snapshot")
        return None

    # Normalize base URL to ensure we hit the HA REST API correctly.
    base = ha_url.rstrip("/")
    if not base.endswith("/api"):
        base = f"{base}/api"

    url = f"{base}/camera_proxy/{camera_entity}"
    print(f"[surveillance] Snapshot URL: {url!r}")
    print(f"[surveillance] HA_HEADERS: {config.HA_HEADERS!r}")
    print(f"[surveillance] Fetching snapshot for camera_entity={camera_entity!r} url={url!r}")
    try:
        async with session.get(url, headers=config.HA_HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                print(
                    f"[surveillance] Snapshot request failed for camera_entity={camera_entity!r} "
                    f"status={resp.status} reason={resp.reason}"
                )
                return None
            data = await resp.read()
            print(
                f"[surveillance] Snapshot fetched for camera_entity={camera_entity!r} "
                f"data_len={len(data) if data is not None else 'None'}"
            )
            return data
    except asyncio.CancelledError:
        print(f"[surveillance] Snapshot fetch cancelled for camera_entity={camera_entity!r}")
        raise
    except Exception as e:
        print(f"[surveillance] Exception while fetching snapshot for {camera_entity!r}: {e!r}")
        return None


async def _producer(
    camera_entities: list[str],
    interval_seconds: float,
    input_queue: asyncio.Queue,
) -> None:
    """
    Every `interval_seconds`:
    - refresh the list of camera entities from the main API (if available)
    - fetch a snapshot from each camera
    - put (camera_entity, image) on the queue
    """
    print(
        f"[surveillance] _producer starting with initial camera_entities={camera_entities}, "
        f"interval_seconds={interval_seconds}"
    )
    async with aiohttp.ClientSession() as session:
        current_camera_entities: list[str] = list(camera_entities)
        camera_refresh_interval = 30.0
        last_camera_refresh: float = 0.0

        while True:
            now = asyncio.get_event_loop().time()
            if now - last_camera_refresh >= camera_refresh_interval:
                print(
                    f"[surveillance] Refresh interval reached; attempting to refresh cameras from DB. "
                    f"now={now}, last_camera_refresh={last_camera_refresh}, "
                    f"camera_refresh_interval={camera_refresh_interval}"
                )
                try:
                    fetched = await _fetch_camera_entities(session)
                    if fetched is not None:
                        current_camera_entities = fetched
                        print(f"[surveillance] Current camera entity_ids: {current_camera_entities}")
                except asyncio.CancelledError:
                    print("[surveillance] _producer camera refresh cancelled")
                    raise
                except Exception as e:
                    print(f"[surveillance] Unexpected error while refreshing cameras: {e!r}")
                finally:
                    last_camera_refresh = now

            print(
                f"[surveillance] _producer loop tick; iterating cameras={current_camera_entities}, "
                f"queue_size={input_queue.qsize()}"
            )
            for camera_entity in current_camera_entities:
                try:
                    image_data = await _fetch_snapshot(session, camera_entity)
                    if image_data is None:
                        print(f"[surveillance] No image data for camera_entity={camera_entity!r}; skipping")
                        continue
                    img = _decode_image(image_data)
                    if img is not None:
                        print(
                            f"[surveillance] Decoded image for camera_entity={camera_entity!r}; "
                            f"putting onto input_queue (current_size={input_queue.qsize()})"
                        )
                        await input_queue.put((camera_entity, img))
                    else:
                        print(
                            f"[surveillance] Failed to decode image bytes for camera_entity={camera_entity!r}"
                        )
                except asyncio.CancelledError:
                    print("[surveillance] _producer cancelled during snapshot loop")
                    raise
                except Exception as e:
                    print(f"[surveillance] Unexpected error in _producer loop for {camera_entity!r}: {e!r}")
            print(f"[surveillance] _producer sleeping for {interval_seconds} seconds")
            await asyncio.sleep(interval_seconds)


async def _consumer(
    results_queue: asyncio.Queue,
    notify_dir: str,
    stop_event: asyncio.Event,
) -> None:
    """Read results from the queue; if any detections, save annotated image to notify_dir.

    Keeps a single "active" notification per camera and detection signature.
    As long as the set/count of detected labels at a camera stays the same
    (e.g., one stranger present for an hour), the same DB notification row is
    updated with the latest image. When the composition changes (e.g., a second
    stranger appears, a kid/resident is added), a new notification row is
    created.
    """
    print(
        f"[surveillance] _consumer starting with notify_dir={notify_dir!r}, "
        f"stop_event_set={stop_event.is_set()}"
    )
    notify_path = Path(notify_dir)
    notify_path.mkdir(parents=True, exist_ok=True)

    last_notifications: dict[str, tuple[str, int, str]] = {}

    while not stop_event.is_set():
        try:
            item = await asyncio.wait_for(results_queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            # No items yet; continue loop
            continue
        except asyncio.CancelledError:
            print("[surveillance] _consumer cancelled while waiting on results_queue")
            break

        results_queue.task_done()
        if len(item) == 4:
            print(f"[surveillance] _consumer received error result payload={item!r}; skipping")
            continue  # error result, skip
        request_id, annotated, detections = item

        if not detections or annotated is None:
            print(
                f"[surveillance] _consumer received empty detections or annotated image for "
                f"request_id={request_id!r}; detections={detections}, annotated_is_none={annotated is None}"
            )
            continue


        labels_signature = "|".join(sorted(d.get("label", "") for d in detections))
        camera_id = str(request_id)

        safe_name = str(request_id).replace(".", "_")
        ts = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{safe_name}_{ts}.jpg"
        out_path = notify_path / filename
        cv2.imwrite(str(out_path), annotated)
        print(
            f"[surveillance] Saved annotated image for camera_id={camera_id!r}, "
            f"labels_signature={labels_signature!r}, path={str(out_path)!r}"
        )

        # Build message "John is detected at front door"
        message = _format_detection_message(detections, request_id)

        # Decide whether to update or create notification
        existing = last_notifications.get(camera_id)
        notification_id: int | None = None

        if existing is not None:
            existing_signature, existing_id, old_image_path = existing
            if existing_signature == labels_signature:
                # Same composition of detections at this camera
                # Update the existing notification and delete the previous image file
                try:
                    old_path = notify_path / old_image_path
                    if old_path.exists():
                        old_path.unlink()
                except Exception as e:
                    print(f"[surveillance] Failed to delete old notification image {old_image_path!r}: {e!r}")

                await _update_detection_notification_db(existing_id, filename, message)
                notification_id = existing_id
                print(
                    f"[surveillance] Updated existing detection notification id={existing_id} "
                    f"for camera_id={camera_id!r} with same signature"
                )

        # If we didn't find a valid cached notification for this signature, insert a new one.
        if notification_id is None:
            created_id = await _create_detection_notification_db(request_id, filename, message)
            if created_id is not None:
                notification_id = created_id
                print(
                    f"[surveillance] Created new detection notification id={created_id} "
                    f"for camera_id={camera_id!r}, labels_signature={labels_signature!r}"
                )
            else:
                print(
                    f"[surveillance] Failed to create new detection notification for "
                    f"camera_id={camera_id!r}, labels_signature={labels_signature!r}"
                )

        # Update cache entry so that continuous presence of the same
        # person(s) (e.g., a stranger at the door) causes updates to the same
        # DB notification, and any change in composition (e.g., new stranger
        # joins) creates a fresh notification.
        if notification_id is not None:
            last_notifications[camera_id] = (labels_signature, notification_id, filename)
            print(
                f"[surveillance] Updated last_notifications cache for camera_id={camera_id!r}: "
                f"(signature={labels_signature!r}, notification_id={notification_id}, filename={filename!r})"
            )
        else:
            print(
                f"[surveillance] No notification_id obtained for camera_id={camera_id!r}, "
                f"labels_signature={labels_signature!r}; cache not updated"
            )


async def run_surveillance(
    camera_entities: list[str] | None = None,
    interval_seconds: float | None = None,
    notify_dir: str | None = None,
) -> asyncio.Task | None:
    """
    Start the vision surveillance loop: poll cameras via HA API, analyze frames, save to notify when detections.
    Returns the asyncio Task so the caller can cancel it on shutdown.
    """
    # Initial load of camera entities (if not explicitly provided)
    if camera_entities is None:
        print("[surveillance] No camera_entities explicitly provided; loading from DB...")
        initial_from_db = await _fetch_camera_entities_from_db()
        if initial_from_db is None:
            print("[surveillance] Could not load initial camera entities from DB; starting with empty list")
            camera_entities = []
        else:
            camera_entities = initial_from_db

    print(f"[surveillance] Starting surveillance with camera_entities={camera_entities}")
    interval_seconds = interval_seconds if interval_seconds is not None else config.VISION_INTERVAL_SECONDS
    notify_dir = notify_dir or config.VISION_NOTIFY_DIR
    print(
        f"[surveillance] Resolved interval_seconds={interval_seconds}, notify_dir={notify_dir!r}, "
        f"HOME_ASSISTANT_URL={config.HOME_ASSISTANT_URL!r}"
    )

    # Allow starting even when no cameras are configured initially; the
    # list can be populated dynamically from the main API.
    if not config.HOME_ASSISTANT_URL or not config.HA_HEADERS:
        print(
            f"[surveillance] HOME_ASSISTANT_URL or HA_HEADERS is not set; cannot start surveillance. "
            f"HOME_ASSISTANT_URL={config.HOME_ASSISTANT_URL!r}, HA_HEADERS_present={bool(config.HA_HEADERS)}"
        )
        return None

    from camerastream import run_analyzer

    input_queue: asyncio.Queue = asyncio.Queue(maxsize=len(camera_entities) * 2 if camera_entities else 10)
    results_queue: asyncio.Queue = asyncio.Queue()
    stop_event = asyncio.Event()

    async def consumer_loop():
        await _consumer(results_queue, notify_dir, stop_event)

    print(
        f"[surveillance] Creating tasks: run_analyzer, _producer, _consumer with "
        f"input_queue_maxsize={input_queue.maxsize}, initial_camera_entities={camera_entities}"
    )
    analyzer_task = asyncio.create_task(run_analyzer(input_queue, results_queue))
    producer_task = asyncio.create_task(_producer(camera_entities, interval_seconds, input_queue))
    consumer_task = asyncio.create_task(consumer_loop())

    async def run_all():
        try:
            print("[surveillance] run_all starting; awaiting producer and consumer tasks")
            await asyncio.gather(producer_task, consumer_task)
        except asyncio.CancelledError:
            print("[surveillance] run_all received CancelledError; shutting down tasks")
            raise
        except Exception as e:
            print(f"[surveillance] Unexpected exception in run_all: {e!r}")
        finally:
            print("[surveillance] run_all cleanup starting")
            stop_event.set()
            try:
                await input_queue.put(None)
            except Exception as e:
                print(f"[surveillance] Failed to put sentinel None into input_queue: {e!r}")

            producer_task.cancel()
            consumer_task.cancel()
            try:
                await producer_task
            except asyncio.CancelledError:
                print("[surveillance] producer_task cancelled and awaited")
            except Exception as e:
                print(f"[surveillance] producer_task finished with exception: {e!r}")

            try:
                await consumer_task
            except asyncio.CancelledError:
                print("[surveillance] consumer_task cancelled and awaited")
            except Exception as e:
                print(f"[surveillance] consumer_task finished with exception: {e!r}")

            analyzer_task.cancel()
            try:
                await analyzer_task
            except asyncio.CancelledError:
                print("[surveillance] analyzer_task cancelled and awaited")
            except Exception as e:
                print(f"[surveillance] analyzer_task finished with exception: {e!r}")
            print("[surveillance] run_all cleanup complete")

    return asyncio.create_task(run_all())
