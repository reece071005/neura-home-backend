from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone, time as dtime
from typing import Any

from ai_app.core.redis_init import get_redis


DEMO_TIME_KEY = "demo:clock"
DUBAI_TZ = timezone(timedelta(hours=4))


def _real_utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _default_state() -> dict[str, Any]:
    now = _real_utc_now()
    return {
        "enabled": False,
        "paused": False,
        "speed": 60.0,
        "base_sim_utc": now.isoformat(),
        "base_real_utc": now.isoformat(),
    }


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


async def get_clock_state() -> dict[str, Any]:
    r = get_redis()
    raw = await r.get(DEMO_TIME_KEY)
    if not raw:
        state = _default_state()
        await r.set(DEMO_TIME_KEY, json.dumps(state))
        return state

    try:
        state = json.loads(raw)
    except Exception:
        state = _default_state()
        await r.set(DEMO_TIME_KEY, json.dumps(state))
        return state

    defaults = _default_state()
    for key, value in defaults.items():
        state.setdefault(key, value)

    return state


def compute_simulated_utc_now_from_state(state: dict[str, Any]) -> datetime:
    real_now = _real_utc_now()

    if not state.get("enabled", False):
        return real_now

    base_sim = _parse_dt(state.get("base_sim_utc"))
    base_real = _parse_dt(state.get("base_real_utc"))
    paused = bool(state.get("paused", False))
    speed = float(state.get("speed", 1.0))

    if base_sim is None:
        return real_now

    if paused or base_real is None:
        return base_sim

    elapsed_real = real_now - base_real
    elapsed_sim = timedelta(seconds=elapsed_real.total_seconds() * speed)
    return base_sim + elapsed_sim


async def get_simulated_utc_now() -> datetime:
    state = await get_clock_state()
    return compute_simulated_utc_now_from_state(state)


async def get_simulated_local_now_dubai() -> datetime:
    return (await get_simulated_utc_now()).astimezone(DUBAI_TZ)


async def build_simulated_expiry_iso(*, cooldown_seconds: int) -> str:
    expires_at = await get_simulated_utc_now() + timedelta(seconds=cooldown_seconds)
    return expires_at.isoformat()


def parse_hhmm_to_time(hhmm: str) -> dtime:
    hh, mm = hhmm.split(":")
    return dtime(hour=int(hh), minute=int(mm))