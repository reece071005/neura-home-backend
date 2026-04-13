from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Optional

from ai_app.core.redis_init import get_redis


@dataclass
class RoomAIPreference:
    enabled: bool


class RoomAIPreferenceStore:
    @staticmethod
    def _key(*, room: str) -> str:
        return f"ai:room_pref:{room}"

    @staticmethod
    async def set_room_ai_enabled(*, room: str, enabled: bool) -> dict:
        r = get_redis()
        pref = RoomAIPreference(enabled=enabled)
        payload = asdict(pref)
        await r.set(RoomAIPreferenceStore._key(room=room), json.dumps(payload))
        return payload

    @staticmethod
    async def get_room_ai_enabled(*, room: str) -> Optional[dict]:
        r = get_redis()
        raw = await r.get(RoomAIPreferenceStore._key(room=room))
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    @staticmethod
    async def delete_room_ai_enabled(*, room: str) -> bool:
        r = get_redis()
        deleted = await r.delete(RoomAIPreferenceStore._key(room=room))
        return bool(deleted)