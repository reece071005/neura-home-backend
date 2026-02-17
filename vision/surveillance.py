"""
Background surveillance: fetch camera snapshots every N seconds (from Home Assistant),
run vision analysis, and save annotated images to the notify folder when anything is detected.
Posts detection notifications to the main API for DB storage.
Self-contained; no dependency on app.
"""
import asyncio
from datetime import datetime
from pathlib import Path

import aiohttp
import cv2
import numpy as np

# Config is in same package
from config import (
    API_URL,
    HA_HEADERS,
    HOME_ASSISTANT_URL,
    VISION_CAMERAS,
    VISION_INTERVAL_SECONDS,
    VISION_NOTIFY_DIR,
)


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


async def _post_notification(camera_entity: str, image_path: str, message: str) -> None:
    """POST detection notification to main API to create DB entry."""
    if not API_URL:
        return
    url = f"{API_URL}/vision/notification"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json={"message": message, "camera_entity": camera_entity, "image_path": image_path},
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status != 200:
                    pass  # log and continue
    except Exception:
        pass


async def _fetch_snapshot(session: aiohttp.ClientSession, camera_entity: str) -> bytes | None:
    """Fetch a single camera snapshot from Home Assistant."""
    url = f"{HOME_ASSISTANT_URL}/camera_proxy/{camera_entity}"
    try:
        async with session.get(url, headers=HA_HEADERS, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return None
            return await resp.read()
    except Exception:
        return None


async def _producer(
    camera_entities: list[str],
    interval_seconds: float,
    input_queue: asyncio.Queue,
) -> None:
    """Every `interval_seconds` fetch a snapshot from each camera and put (camera_entity, image) on the queue."""
    async with aiohttp.ClientSession() as session:
        while True:
            for camera_entity in camera_entities:
                try:
                    image_data = await _fetch_snapshot(session, camera_entity)
                    if image_data is None:
                        continue
                    img = _decode_image(image_data)
                    if img is not None:
                        await input_queue.put((camera_entity, img))
                except asyncio.CancelledError:
                    raise
                except Exception:
                    pass
            await asyncio.sleep(interval_seconds)


async def _consumer(
    results_queue: asyncio.Queue,
    notify_dir: str,
    stop_event: asyncio.Event,
) -> None:
    """Read results from the queue; if any detections, save annotated image to notify_dir.

    Also applies a small de-duplication window so that repeated, identical
    detections from the same camera within a short time do not create
    multiple near-identical notification images.
    """
    notify_path = Path(notify_dir)
    notify_path.mkdir(parents=True, exist_ok=True)

    # Track the last time we created a notification for a given
    # (camera_entity, labels_signature). This is in-memory only and is
    # reset when the process restarts, which is fine for our use case.
    last_notification_times: dict[tuple[str, str], datetime] = {}
    # Minimum time between notifications with the same labels for the same camera.
    # This prevents duplicate images/notifications when the model returns
    # similar detections on consecutive frames.
    duplicate_suppress_seconds = 30

    while not stop_event.is_set():
        try:
            item = await asyncio.wait_for(results_queue.get(), timeout=1.0)
        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            break

        results_queue.task_done()
        if len(item) == 4:
            continue  # error result, skip
        request_id, annotated, detections = item

        if not detections or annotated is None:
            continue

        # Build a stable "labels signature" for this detection result so we can
        # suppress identical notifications in a short time window.
        labels_signature = "|".join(sorted(d.get("label", "") for d in detections))
        now = datetime.utcnow()
        key = (str(request_id), labels_signature)
        last_ts = last_notification_times.get(key)
        if last_ts is not None and (now - last_ts).total_seconds() < duplicate_suppress_seconds:
            # Too soon since the last identical notification; skip creating another
            # image/notification to avoid duplicates.
            continue
        last_notification_times[key] = now

        safe_name = str(request_id).replace(".", "_")
        ts = datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{safe_name}_{ts}.jpg"
        out_path = notify_path / filename
        cv2.imwrite(str(out_path), annotated)

        # Build message and create DB entry via main API (e.g. "John is detected at front door")
        message = _format_detection_message(detections, request_id)
        await _post_notification(request_id, filename, message)


async def run_surveillance(
    camera_entities: list[str] | None = None,
    interval_seconds: float | None = None,
    notify_dir: str | None = None,
) -> asyncio.Task | None:
    """
    Start the vision surveillance loop: poll cameras via HA API, analyze frames, save to notify when detections.
    Returns the asyncio Task so the caller can cancel it on shutdown.
    """
    camera_entities = camera_entities or VISION_CAMERAS
    interval_seconds = interval_seconds if interval_seconds is not None else VISION_INTERVAL_SECONDS
    notify_dir = notify_dir or VISION_NOTIFY_DIR

    if not camera_entities or not HOME_ASSISTANT_URL or not HA_HEADERS:
        return None

    from camerastream import run_analyzer

    input_queue: asyncio.Queue = asyncio.Queue(maxsize=len(camera_entities) * 2)
    results_queue: asyncio.Queue = asyncio.Queue()
    stop_event = asyncio.Event()

    async def consumer_loop():
        await _consumer(results_queue, notify_dir, stop_event)

    analyzer_task = asyncio.create_task(run_analyzer(input_queue, results_queue))
    producer_task = asyncio.create_task(_producer(camera_entities, interval_seconds, input_queue))
    consumer_task = asyncio.create_task(consumer_loop())

    async def run_all():
        try:
            await asyncio.gather(producer_task, consumer_task)
        except asyncio.CancelledError:
            pass
        finally:
            stop_event.set()
            await input_queue.put(None)
            producer_task.cancel()
            consumer_task.cancel()
            try:
                await producer_task
            except asyncio.CancelledError:
                pass
            try:
                await consumer_task
            except asyncio.CancelledError:
                pass
            analyzer_task.cancel()
            try:
                await analyzer_task
            except asyncio.CancelledError:
                pass

    return asyncio.create_task(run_all())
