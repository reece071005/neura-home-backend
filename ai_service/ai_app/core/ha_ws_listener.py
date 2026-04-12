import asyncio
import json
import os
from typing import Any

import aiohttp
import websockets

from ai_app.services.influx_logger import InfluxLogger
from ai_app.core.demo_time import get_simulated_utc_now
from ai_app.services.room_client import fetch_all_rooms


APP_URL = os.getenv("APP_URL", "http://api:8000")
AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://ai_service:8002")


_HA_BASE_URL: str | None = None
_HA_TOKEN: str | None = None


async def fetch_home_assistant_config_from_backend() -> tuple[str, str]:
    url = f"{APP_URL}/internal/home-assistant-config"

    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"Failed to fetch HA config from backend: status={resp.status}, body={text}")

            data = await resp.json()

    base_url = data.get("url")
    token = data.get("token")

    if not base_url or not token:
        raise RuntimeError("Backend returned incomplete HA config.")

    return base_url.rstrip("/"), token


def build_ws_url_from_base(base_url: str) -> str:
    if base_url.startswith("https://"):
        ws_url = "wss://" + base_url[len("https://"):]
    elif base_url.startswith("http://"):
        ws_url = "ws://" + base_url[len("http://"):]
    elif base_url.startswith("wss://") or base_url.startswith("ws://"):
        ws_url = base_url
    else:
        ws_url = "ws://" + base_url

    if ws_url.endswith("/api/websocket"):
        return ws_url
    if ws_url.endswith("/api"):
        return ws_url + "/websocket"
    return ws_url + "/api/websocket"


async def refresh_home_assistant_config() -> None:
    global _HA_BASE_URL, _HA_TOKEN
    _HA_BASE_URL, _HA_TOKEN = await fetch_home_assistant_config_from_backend()


async def get_home_assistant_config() -> tuple[str, str]:
    global _HA_BASE_URL, _HA_TOKEN
    if not _HA_BASE_URL or not _HA_TOKEN:
        await refresh_home_assistant_config()
    return _HA_BASE_URL, _HA_TOKEN


async def get_allowed_entity_ids() -> set[str]:
    try:
        rooms = await fetch_all_rooms()
    except Exception as e:
        print(f"[WS] Failed to fetch rooms for entity filtering: {e}")
        return set()

    allowed = set()
    for room in rooms:
        for entity_id in room.get("entity_ids", []) or []:
            allowed.add(str(entity_id))
    return allowed


def _is_supported_domain(entity_id: str) -> bool:
    if "." not in entity_id:
        return False
    domain = entity_id.split(".", 1)[0]
    return domain in {"light", "climate", "cover", "fan", "binary_sensor"}


async def fetch_all_homeassistant_states() -> list[dict[str, Any]]:
    base_url, token = await get_home_assistant_config()
    url = f"{base_url}/api/states"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise RuntimeError(f"HA states request failed: status={resp.status}, body={text}")
            return await resp.json()


async def execute_command(entity_id: str, param):
    device_type = entity_id.split(".")[0]
    param_map = {
        "light": "state",
        "climate": "temperature",
        "cover": "position",
    }

    payload_key = param_map.get(device_type)
    if payload_key is None:
        return {"ok": False, "error": f"Unsupported domain: {device_type}"}

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{APP_URL}/homecontrollers/{device_type}",
            json={"entity_id": entity_id, payload_key: param},
        ) as resp:
            try:
                return await resp.json()
            except Exception:
                return {"ok": False, "status": resp.status}


async def create_ai_notification(
    *,
    message: str,
    room: str,
    entity_id: str,
    notification_type: str,
    action_type: str,
    meta: dict | None = None,
):
    payload = {
        "message": message,
        "room": room,
        "entity_id": entity_id,
        "notification_type": notification_type,
        "action_type": action_type,
        "meta": meta or {},
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{APP_URL}/ai-notifications/notification",
            json=payload,
        ) as resp:
            if resp.status >= 400:
                try:
                    text = await resp.text()
                except Exception:
                    text = "<no body>"
                print(f"[WS] Failed to create AI notification: status={resp.status}, body={text}")


async def handle_motion_event(entity_id: str):
    print(f"[WS] Motion detected: {entity_id}")

    room_mapping = {
        "binary_sensor.kids_rooms_occupancy": "reece_room",
        "binary_sensor.guest_room_occupancy": "guest_room",
        "binary_sensor.master_bedroom_presence_sensor_presence": "Master Bedroom",
    }

    room = room_mapping.get(entity_id)
    if not room:
        return

    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{AI_SERVICE_URL}/ai/smart-suggestions",
            params={"room": room},
        ) as resp:
            if resp.status != 200:
                print(f"[WS] AI service error: status={resp.status}")
                return

            ai_data = await resp.json()

    suggestions = ai_data.get("suggestions", [])

    for suggestion in suggestions:
        suggestion_type = suggestion.get("type")
        action = suggestion.get("action", {})
        entity = action.get("entity_id")

        if not entity:
            continue

        if suggestion_type == "light":
            result = await execute_command(entity, "on")
            if result and (result.get("success") is True or result.get("ok") is True):
                await create_ai_notification(
                    message=f"AI turned on {entity} after motion was detected in {room}.",
                    room=room,
                    entity_id=entity,
                    notification_type="executed",
                    action_type="light",
                    meta={
                        "trigger": "motion",
                        "source_sensor": entity_id,
                        "suggestion": suggestion,
                    },
                )

        elif suggestion_type == "climate":
            temp = action.get("temperature")
            result = await execute_command(entity, temp)
            if result and (result.get("success") is True or result.get("ok") is True):
                await create_ai_notification(
                    message=f"AI set {entity} to {temp}°C for {room}.",
                    room=room,
                    entity_id=entity,
                    notification_type="executed",
                    action_type="climate",
                    meta={
                        "trigger": "motion_or_preconditioning",
                        "source_sensor": entity_id,
                        "temperature": temp,
                        "suggestion": suggestion,
                    },
                )

        elif suggestion_type == "cover":
            position = action.get("position")
            if position is not None:
                result = await execute_command(entity, int(position))
                if result and (result.get("success") is True or result.get("ok") is True):
                    await create_ai_notification(
                        message=f"AI adjusted {entity} to position {int(position)} in {room}.",
                        room=room,
                        entity_id=entity,
                        notification_type="executed",
                        action_type="cover",
                        meta={
                            "trigger": "motion",
                            "source_sensor": entity_id,
                            "position": int(position),
                            "suggestion": suggestion,
                        },
                    )


async def log_state_change_to_influx(entity_id: str, new_state: dict):
    if "." not in entity_id:
        return

    domain = entity_id.split(".", 1)[0]
    state = new_state.get("state")
    attributes = new_state.get("attributes", {}) or {}

    await InfluxLogger.log_device_state(
        entity_id=entity_id,
        domain=domain,
        state=state,
        attributes=attributes,
        area=None,
        source="ws_state_changed",
        ts=await get_simulated_utc_now(),
    )


async def run_startup_snapshot():
    try:
        states = await fetch_all_homeassistant_states()
        allowed_entity_ids = await get_allowed_entity_ids()

        if not allowed_entity_ids:
            print("[WS] Startup snapshot skipped: no allowed entity IDs found from rooms.")
            return

        ts = await get_simulated_utc_now()
        written = 0

        for item in states:
            entity_id = item.get("entity_id")
            if not entity_id or "." not in entity_id:
                continue

            if entity_id not in allowed_entity_ids:
                continue

            if not _is_supported_domain(entity_id):
                continue

            domain = entity_id.split(".", 1)[0]
            state = item.get("state")
            attributes = item.get("attributes", {}) or {}

            await InfluxLogger.log_device_state(
                entity_id=entity_id,
                domain=domain,
                state=state,
                attributes=attributes,
                area=None,
                source="startup_snapshot",
                ts=ts,
            )
            written += 1

        print(f"[WS] Startup snapshot written to Influx: {written} states")
    except Exception as e:
        print(f"[WS] Startup snapshot failed: {e}")
        raise


async def start_ha_websocket_listener():
    print("[WS] Listener starting...")

    while True:
        try:
            base_url, token = await get_home_assistant_config()
            ws_url = build_ws_url_from_base(base_url)

            async with websockets.connect(ws_url) as ws:
                print(f"[WS] Connected to Home Assistant at {ws_url}")

                await ws.recv()

                await ws.send(
                    json.dumps(
                        {
                            "type": "auth",
                            "access_token": token,
                        }
                    )
                )

                await ws.recv()

                await ws.send(
                    json.dumps(
                        {
                            "id": 1,
                            "type": "subscribe_events",
                            "event_type": "state_changed",
                        }
                    )
                )

                await ws.recv()

                print("[WS] Listening for state_changed events...")

                while True:
                    raw = await ws.recv()
                    data = json.loads(raw)

                    if data.get("type") != "event":
                        continue

                    event = data.get("event", {})
                    event_data = event.get("data", {})

                    entity_id = event_data.get("entity_id")
                    new_state = event_data.get("new_state", {})

                    if not entity_id or not new_state:
                        continue

                    allowed_entity_ids = await get_allowed_entity_ids()

                    if entity_id in allowed_entity_ids and _is_supported_domain(entity_id):
                        try:
                            await log_state_change_to_influx(entity_id, new_state)
                        except Exception as e:
                            print(f"[WS] Failed to log state change for {entity_id}: {e}")

                    if entity_id.startswith("binary_sensor") and new_state.get("state") == "on":
                        await handle_motion_event(entity_id)

        except Exception as e:
            print(f"[WS] Error: {e}. Reconnecting in 5 seconds...")
            try:
                await refresh_home_assistant_config()
            except Exception as refresh_err:
                print(f"[WS] Failed to refresh HA config: {refresh_err}")
            await asyncio.sleep(5)