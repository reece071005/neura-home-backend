from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from ai_app.core.redis_init import get_redis
from ai_app.core.demo_time import build_simulated_expiry_iso, get_simulated_utc_now


@dataclass(frozen=True)
class CooldownConfig:
    cooldown_seconds: int = 300  # 5 simulated minutes


class SuggestionStore:
    @staticmethod
    async def is_in_cooldown(*, room: str, suggestion_type: str, entity_id: str) -> bool:
        r = get_redis()
        key = SuggestionStore._cooldown_key(room=room, suggestion_type=suggestion_type, entity_id=entity_id)
        raw = await r.get(key)
        if not raw:
            return False

        try:
            payload = json.loads(raw)
            expires_at_raw = payload.get("expires_at_sim_utc")
            if not expires_at_raw:
                return False

            expires_at = datetime.fromisoformat(expires_at_raw)
            now_sim = await get_simulated_utc_now()

            if now_sim >= expires_at:
                await r.delete(key)
                return False

            return True
        except Exception:
            await r.delete(key)
            return False

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

        payload = {
            "expires_at_sim_utc": await build_simulated_expiry_iso(cooldown_seconds=cfg.cooldown_seconds)
        }

        await r.set(key, json.dumps(payload))

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
        now_sim = await get_simulated_utc_now()

        payload = {
            "ts_utc": now_sim.isoformat(),
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