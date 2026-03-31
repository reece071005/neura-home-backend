import asyncio
from ai_app.services.room_client import fetch_all_rooms
from ai_app.ai.predictor import Predictor


async def run_ai_for_all_rooms():
    rooms = await fetch_all_rooms()

    for room in rooms:
        room_name = room["name"]

        try:
            result = await Predictor.smart_room_suggestions(room=room_name)
            # Here you could auto-execute or log
            print(f"[AI] Suggestions for {room_name}: {len(result.get('suggestions', []))}")
        except Exception as e:
            print(f"[AI] Error processing room {room_name}: {e}")


async def automation_loop(interval_seconds: int = 60):
    while True:
        try:
            await run_ai_for_all_rooms()
        except Exception as e:
            print(f"[AI_LOOP] {e}")

        await asyncio.sleep(interval_seconds)