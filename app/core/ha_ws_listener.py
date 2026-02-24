import asyncio
import json
import os
import websockets
import aiohttp

from app.core.homeassistant import LightControl, ClimateControl, CoverControl
from app import schemas

HA_WS_URL = os.getenv("HA_WS_URL")
HA_TOKEN = os.getenv("HA_TOKEN")

AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://ai_service:8000")


async def handle_motion_event(entity_id: str):
    """
    Called when motion sensor turns ON.
    Triggers AI automation.
    """
    print(f"[WS] Motion detected: {entity_id}")

    # Map motion sensor to room
    room_mapping = {
        "binary_sensor.kids_rooms_occupancy": "reece_room",
        "binary_sensor.guest_room_occupancy": "guest_room",
        # add others here
    }

    room = room_mapping.get(entity_id)
    if not room:
        return

    # Call AI smart suggestions
    async with aiohttp.ClientSession() as session:
        async with session.get(
            f"{AI_SERVICE_URL}/ai/smart-suggestions",
            params={"room": room}
        ) as resp:
            if resp.status != 200:
                print("AI service error")
                return

            ai_data = await resp.json()

    suggestions = ai_data.get("suggestions", [])

    for suggestion in suggestions:
        suggestion_type = suggestion.get("type")
        action = suggestion.get("action", {})
        entity = action.get("entity_id")

        if suggestion_type == "light":
            light_state = schemas.LightState(entity_id=entity, state="on")
            await LightControl.turn_on_light(light_state)

        elif suggestion_type == "climate":
            temperature = action.get("temperature")
            await ClimateControl.control_climate(
                entity_id=entity,
                temperature=temperature
            )

        elif suggestion_type == "cover":
            position = action.get("position")
            await CoverControl.set_cover_position(
                cover_entity=entity,
                position=int(position)
            )


async def start_ha_websocket_listener():
    print("[WS] Listener starting...✅ ✅ ✅ ✅ ✅ ✅ ✅ ")
    """
    Connects to HA WebSocket and listens for motion events.
    """
    if not HA_WS_URL or not HA_TOKEN:
        print("HA_WS_URL or HA_TOKEN not configured.")
        return

    while True:
        try:
            async with websockets.connect(HA_WS_URL) as ws:
                print("[WS] Connected to Home Assistant")

                # Receive auth_required
                await ws.recv()

                # Authenticate
                await ws.send(json.dumps({
                    "type": "auth",
                    "access_token": HA_TOKEN
                }))

                await ws.recv()  # auth_ok

                # Subscribe to state_changed events
                await ws.send(json.dumps({
                    "id": 1,
                    "type": "subscribe_events",
                    "event_type": "state_changed"
                }))

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