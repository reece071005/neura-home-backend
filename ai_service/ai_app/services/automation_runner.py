import asyncio
from datetime import datetime, timedelta, timezone

from ai_app.services.room_client import fetch_all_rooms
from ai_app.ai.predictor import Predictor
from ai_app.ai.room_trainer import RoomTrainer
from ai_app.ai.training_preference_store import TrainingPreferenceStore


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


def _is_due(*, frequency: str, last_trained_at: str | None) -> bool:
    if frequency == "manual":
        return False

    if not last_trained_at:
        return True

    try:
        last_dt = datetime.fromisoformat(last_trained_at)
        if last_dt.tzinfo is None:
            last_dt = last_dt.replace(tzinfo=timezone.utc)
    except Exception:
        return True

    now = datetime.now(timezone.utc)

    if frequency == "daily":
        return now - last_dt >= timedelta(days=1)

    if frequency == "weekly":
        return now - last_dt >= timedelta(days=7)

    if frequency == "monthly":
        return now - last_dt >= timedelta(days=30)

    return False


async def retrain_due_rooms(days: int = 30):
    prefs = await TrainingPreferenceStore.list_all_training_preferences()

    for pref in prefs:
        room = pref["room"]
        enabled = bool(pref.get("enabled", True))
        frequency = str(pref.get("frequency", "manual"))
        last_trained_at = pref.get("last_trained_at")

        if not enabled:
            continue

        if not _is_due(frequency=frequency, last_trained_at=last_trained_at):
            continue

        try:
            result = RoomTrainer.train_room(room=room, days=days)
            print(f"[RETRAIN] room={room} result={result}")
            await TrainingPreferenceStore.mark_trained_now(room=room)
        except Exception as e:
            print(f"[RETRAIN] Failed for room={room}: {e}")


async def retrain_loop():
    check_interval_minutes = 10
    lookback_days = 30

    print(f"[RETRAIN] Preference-based retraining loop running every {check_interval_minutes} minutes.")

    while True:
        try:
            await retrain_due_rooms(days=lookback_days)
        except Exception as e:
            print(f"[RETRAIN_LOOP] {e}")

        await asyncio.sleep(check_interval_minutes * 60)