from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from ai_app.core.redis_init import get_redis


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class CooldownConfig:
    cooldown_seconds: int = 300  # 5 minutes


class SuggestionStore:
    @staticmethod
    async def is_in_cooldown(*, room: str, suggestion_type: str, entity_id: str) -> bool:
        r = get_redis()
        key = SuggestionStore._cooldown_key(room=room, suggestion_type=suggestion_type, entity_id=entity_id)
        val = await r.get(key)
        return val is not None

    @staticmethod
    async def set_cooldown(
        *,
        room: str,
        suggestion_type: str,
        entity_id: str,
        cfg: CooldownConfig = CooldownConfig(),
    ) -> None:
        r = get_redis()
        key = SuggestionStore._cooldown_key(room=room, suggestion_type=suggestion_type, entity_id=entity_id)
        await r.set(key, "1", ex=cfg.cooldown_seconds)

    @staticmethod
    async def log_feedback(
        *,
        user_id: int,
        room: str,
        suggestion_type: str,
        entity_id: str,
        decision: str,
        meta: Optional[dict[str, Any]] = None,
    ) -> None:
        r = get_redis()
        meta = meta or {}

        payload = {
            "ts_utc": _utc_now().isoformat(),
            "user_id": user_id,
            "room": room,
            "type": suggestion_type,
            "entity_id": entity_id,
            "decision": decision,
            "meta": meta,
        }

        await r.lpush("ai:feedback", json.dumps(payload))
        await r.lpush(f"ai:feedback:user:{user_id}", json.dumps(payload))

    @staticmethod
    def _cooldown_key(*, room: str, suggestion_type: str, entity_id: str) -> str:
        return f"ai:cooldown:{room}:{suggestion_type}:{entity_id}"
