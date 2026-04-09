import asyncio
import os

from ai_app.services.room_client import fetch_all_rooms
from ai_app.ai.predictor import Predictor
from ai_app.ai.room_trainer import RoomTrainer


async def run_ai_for_all_rooms():
    rooms = await fetch_all_rooms()

    for room in rooms:
        room_name = room["name"]

        try:
            result = await Predictor.smart_room_suggestions(room=room_name)
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


async def retrain_all_rooms(days: int = 30):
    rooms = await fetch_all_rooms()

    for room in rooms:
        room_name = room["name"]
        try:
            result = RoomTrainer.train_room(room=room_name, days=days)
            print(f"[RETRAIN] {room_name}: {result}")
        except Exception as e:
            print(f"[RETRAIN] Failed for {room_name}: {e}")


async def retrain_loop():
    enabled = os.getenv("AUTO_RETRAIN_ENABLED", "false").strip().lower() in {"1", "true", "yes", "y"}
    interval_hours = int(os.getenv("AUTO_RETRAIN_INTERVAL_HOURS", "12"))
    days = int(os.getenv("AUTO_RETRAIN_DAYS", "30"))

    if not enabled:
        print("[RETRAIN] Auto retraining disabled.")
        while True:
            await asyncio.sleep(3600)

    print(f"[RETRAIN] Auto retraining enabled. interval_hours={interval_hours}, days={days}")

    while True:
        try:
            await retrain_all_rooms(days=days)
        except Exception as e:
            print(f"[RETRAIN_LOOP] {e}")

        await asyncio.sleep(interval_hours * 3600)