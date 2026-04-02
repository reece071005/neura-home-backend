from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Any, Optional

from ai_app.core.redis_init import get_redis


@dataclass
class ClimatePreference:
    enabled: bool = True
    arrival_time_weekday: str = "18:30"
    arrival_time_weekend: str = "13:00"
    lead_minutes: int = 30
    min_temp_delta: float = 1.0
    fallback_setpoint: float = 24.0
    active_confidence_threshold: float = 0.65
    min_setpoint_c: float = 18.0
    max_setpoint_c: float = 28.0


class UserPreferenceStore:
    @staticmethod
    def _key(user_id: int, room: str) -> str:
        return f"ai:user_prefs:{user_id}:{room}:climate"

    @staticmethod
    async def get_climate_preferences(*, user_id: int, room: str) -> Optional[dict[str, Any]]:
        r = get_redis()
        raw = await r.get(UserPreferenceStore._key(user_id, room))
        if not raw:
            return None

        try:
            data = json.loads(raw)
            return ClimatePreference(**data).__dict__
        except Exception:
            return None

    @staticmethod
    async def set_climate_preferences(
        *,
        user_id: int,
        room: str,
        preferences: ClimatePreference,
    ) -> dict[str, Any]:
        r = get_redis()
        payload = asdict(preferences)
        await r.set(UserPreferenceStore._key(user_id, room), json.dumps(payload))
        return payload

    @staticmethod
    async def delete_climate_preferences(*, user_id: int, room: str) -> bool:
        r = get_redis()
        deleted = await r.delete(UserPreferenceStore._key(user_id, room))
        return bool(deleted)