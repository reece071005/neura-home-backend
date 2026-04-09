import asyncio
import json
import os
from typing import Any

import aiohttp
import websockets

from ai_app.services.influx_logger import InfluxLogger
from ai_app.core.demo_time import get_simulated_utc_now


HA_WS_URL = os.getenv("HA_WS_URL")
HA_TOKEN = os.getenv("HA_TOKEN")

AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://ai_service:8002")
APP_URL = os.getenv("APP_URL", "http://api:8000")


def _build_ha_api_base() -> str:
    if not HA_WS_URL:
        raise RuntimeError("HA_WS_URL is not configured.")

    url = HA_WS_URL.strip()

    if url.startswith("ws://"):
        base = "http://" + url[len("ws://"):]
    elif url.startswith("wss://"):
        base = "https://" + url[len("wss://"):]
    else:
        base = url

    if base.endswith("/api/websocket"):
        base = base[: -len("/api/websocket")]
    elif base.endswith("/websocket"):
        base = base[: -len("/websocket")]

    return base.rstrip("/")


async def fetch_all_homeassistant_states() -> list[dict[str, Any]]:
    if not HA_TOKEN:
        raise RuntimeError("HA_TOKEN is not configured.")

    base = _build_ha_api_base()
    url = f"{base}/api/states"
    headers = {"Authorization": f"Bearer {HA_TOKEN}", "Content-Type": "application/json"}

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


async def handle_motion_event(entity_id: str):
    print(f"[WS] Motion detected: {entity_id}")

    room_mapping = {
        "binary_sensor.kids_rooms_occupancy": "reece_room",
        "binary_sensor.guest_room_occupancy": "guest_room",
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
            if result and result.get("success", False):
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
            if result and result.get("success", False):
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
                if result and result.get("success", False):
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
        ts = await get_simulated_utc_now()
        written = 0

        for item in states:
            entity_id = item.get("entity_id")
            if not entity_id or "." not in entity_id:
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


async def start_ha_websocket_listener():
    print("[WS] Listener starting...")

    if not HA_WS_URL or not HA_TOKEN:
        print("[WS] HA_WS_URL or HA_TOKEN not configured. Skipping listener.")
        return

    while True:
        try:
            async with websockets.connect(HA_WS_URL) as ws:
                print("[WS] Connected to Home Assistant")

                await ws.recv()

                await ws.send(
                    json.dumps(
                        {
                            "type": "auth",
                            "access_token": HA_TOKEN,
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

                    try:
                        await log_state_change_to_influx(entity_id, new_state)
                    except Exception as e:
                        print(f"[WS] Failed to log state change for {entity_id}: {e}")

                    if entity_id.startswith("binary_sensor") and new_state.get("state") == "on":
                        await handle_motion_event(entity_id)

        except Exception as e:
            print(f"[WS] Error: {e}. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)

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