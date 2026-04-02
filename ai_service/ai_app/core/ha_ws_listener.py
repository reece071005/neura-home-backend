import asyncio
import json
import os

import aiohttp
import websockets


HA_WS_URL = os.getenv("HA_WS_URL")
HA_TOKEN = os.getenv("HA_TOKEN")

AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://ai_service:8002")
APP_URL = os.getenv("APP_URL", "http://api:8000")


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
            await execute_command(entity, "on")

        elif suggestion_type == "climate":
            await execute_command(entity, action.get("temperature"))

        elif suggestion_type == "cover":
            position = action.get("position")
            if position is not None:
                await execute_command(entity, int(position))


async def start_ha_websocket_listener():
    print("[WS] Listener starting...")

    if not HA_WS_URL or not HA_TOKEN:
        print("[WS] HA_WS_URL or HA_TOKEN not configured. Skipping listener.")
        return

    while True:
        try:
            async with websockets.connect(HA_WS_URL) as ws:
                print("[WS] Connected to Home Assistant")

                # auth_required
                await ws.recv()

                await ws.send(
                    json.dumps(
                        {
                            "type": "auth",
                            "access_token": HA_TOKEN,
                        }
                    )
                )

                # auth_ok
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

                print("[WS] Listening for motion events...")

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

                    if not entity_id.startswith("binary_sensor"):
                        continue

                    if new_state.get("state") == "on":
                        await handle_motion_event(entity_id)

        except Exception as e:
            print(f"[WS] Error: {e}. Reconnecting in 5 seconds...")
            await asyncio.sleep(5)