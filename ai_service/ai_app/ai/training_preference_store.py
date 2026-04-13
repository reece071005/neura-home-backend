from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Optional, Literal

from ai_app.core.redis_init import get_redis


TrainingFrequency = Literal["manual", "daily", "weekly", "monthly"]


@dataclass
class TrainingPreference:
    enabled: bool = True
    frequency: TrainingFrequency = "manual"
    last_trained_at: Optional[str] = None


class TrainingPreferenceStore:
    @staticmethod
    def _key(*, room: str) -> str:
        return f"ai:training_pref:{room}"

    @staticmethod
    def _index_key() -> str:
        return "ai:training_pref:index"

    @staticmethod
    async def set_training_preferences(
        *,
        room: str,
        enabled: bool,
        frequency: TrainingFrequency,
    ) -> dict:
        r = get_redis()

        payload = TrainingPreference(
            enabled=enabled,
            frequency=frequency,
            last_trained_at=None,
        )

        existing = await TrainingPreferenceStore.get_training_preferences(room=room)
        if existing and existing.get("last_trained_at"):
            payload.last_trained_at = existing["last_trained_at"]

        data = asdict(payload)
        await r.set(TrainingPreferenceStore._key(room=room), json.dumps(data))
        await r.sadd(TrainingPreferenceStore._index_key(), room)
        return data

    @staticmethod
    async def get_training_preferences(*, room: str) -> Optional[dict]:
        r = get_redis()
        raw = await r.get(TrainingPreferenceStore._key(room=room))
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    @staticmethod
    async def delete_training_preferences(*, room: str) -> bool:
        r = get_redis()
        deleted = await r.delete(TrainingPreferenceStore._key(room=room))
        await r.srem(TrainingPreferenceStore._index_key(), room)
        return bool(deleted)

    @staticmethod
    async def mark_trained_now(*, room: str) -> Optional[dict]:
        r = get_redis()
        current = await TrainingPreferenceStore.get_training_preferences(room=room)
        if not current:
            return None

        current["last_trained_at"] = datetime.now(timezone.utc).isoformat()
        await r.set(TrainingPreferenceStore._key(room=room), json.dumps(current))
        return current

    @staticmethod
    async def list_all_training_preferences() -> list[dict]:
        r = get_redis()
        rooms = await r.smembers(TrainingPreferenceStore._index_key())
        results: list[dict] = []

        for room in rooms:
            pref = await TrainingPreferenceStore.get_training_preferences(room=room)
            if pref is None:
                continue

            results.append(
                {
                    "room": room,
                    **pref,
                }
            )

        return results