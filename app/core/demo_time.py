from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone, time as dtime
from typing import Any

from app.core.redis_init import get_redis


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


async def save_clock_state(state: dict[str, Any]) -> dict[str, Any]:
    r = get_redis()
    await r.set(DEMO_TIME_KEY, json.dumps(state))
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


async def set_demo_enabled(enabled: bool) -> dict[str, Any]:
    state = await get_clock_state()
    now_real = _real_utc_now()
    now_sim = compute_simulated_utc_now_from_state(state)

    state["enabled"] = enabled
    state["base_sim_utc"] = now_sim.isoformat()
    state["base_real_utc"] = now_real.isoformat()

    if not enabled:
        state["paused"] = False

    return await save_clock_state(state)


async def set_speed(speed: float) -> dict[str, Any]:
    if speed <= 0:
        raise ValueError("speed must be > 0")

    state = await get_clock_state()
    now_real = _real_utc_now()
    now_sim = compute_simulated_utc_now_from_state(state)

    state["speed"] = float(speed)
    state["base_sim_utc"] = now_sim.isoformat()
    state["base_real_utc"] = now_real.isoformat()

    return await save_clock_state(state)


async def pause_clock() -> dict[str, Any]:
    state = await get_clock_state()
    now_sim = compute_simulated_utc_now_from_state(state)

    state["paused"] = True
    state["base_sim_utc"] = now_sim.isoformat()
    state["base_real_utc"] = _real_utc_now().isoformat()

    return await save_clock_state(state)


async def resume_clock() -> dict[str, Any]:
    state = await get_clock_state()
    now_sim = compute_simulated_utc_now_from_state(state)

    state["paused"] = False
    state["base_sim_utc"] = now_sim.isoformat()
    state["base_real_utc"] = _real_utc_now().isoformat()

    return await save_clock_state(state)


async def set_simulated_utc(dt_utc: datetime) -> dict[str, Any]:
    if dt_utc.tzinfo is None:
        dt_utc = dt_utc.replace(tzinfo=timezone.utc)
    dt_utc = dt_utc.astimezone(timezone.utc)

    state = await get_clock_state()
    state["enabled"] = True
    state["base_sim_utc"] = dt_utc.isoformat()
    state["base_real_utc"] = _real_utc_now().isoformat()

    return await save_clock_state(state)


async def set_simulated_local_dubai(dt_local: datetime) -> dict[str, Any]:
    if dt_local.tzinfo is None:
        dt_local = dt_local.replace(tzinfo=DUBAI_TZ)
    dt_utc = dt_local.astimezone(timezone.utc)
    return await set_simulated_utc(dt_utc)


async def jump_to_local_time(hhmm: str, keep_date: bool = True) -> dict[str, Any]:
    parts = hhmm.strip().split(":")
    if len(parts) != 2:
        raise ValueError("hhmm must be in HH:MM format")

    hh, mm = int(parts[0]), int(parts[1])

    current_local = await get_simulated_local_now_dubai()
    if keep_date:
        new_local = current_local.replace(hour=hh, minute=mm, second=0, microsecond=0)
    else:
        now_real_local = _real_utc_now().astimezone(DUBAI_TZ)
        new_local = now_real_local.replace(hour=hh, minute=mm, second=0, microsecond=0)

    return await set_simulated_local_dubai(new_local)


async def advance_simulated_time(*, days: int = 0, hours: int = 0, minutes: int = 0, seconds: int = 0) -> dict[str, Any]:
    current = await get_simulated_utc_now()
    new_dt = current + timedelta(days=days, hours=hours, minutes=minutes, seconds=seconds)
    return await set_simulated_utc(new_dt)


async def reset_demo_clock() -> dict[str, Any]:
    state = _default_state()
    return await save_clock_state(state)


async def get_clock_payload() -> dict[str, Any]:
    state = await get_clock_state()
    sim_utc = compute_simulated_utc_now_from_state(state)
    sim_local = sim_utc.astimezone(DUBAI_TZ)

    return {
        "enabled": bool(state.get("enabled", False)),
        "paused": bool(state.get("paused", False)),
        "speed": float(state.get("speed", 1.0)),
        "simulated_utc": sim_utc.isoformat(),
        "simulated_local_dubai": sim_local.isoformat(),
        "simulated_date_dubai": sim_local.strftime("%Y-%m-%d"),
        "simulated_time_dubai": sim_local.strftime("%H:%M:%S"),
        "timezone": "Asia/Dubai",
        "label": "Neura Demo Clock",
    }


async def get_current_simulated_epoch_seconds() -> int:
    return int((await get_simulated_utc_now()).timestamp())


async def build_simulated_expiry_iso(*, cooldown_seconds: int) -> str:
    expires_at = await get_simulated_utc_now() + timedelta(seconds=cooldown_seconds)
    return expires_at.isoformat()


def parse_hhmm_to_time(hhmm: str) -> dtime:
    hh, mm = hhmm.split(":")
    return dtime(hour=int(hh), minute=int(mm))