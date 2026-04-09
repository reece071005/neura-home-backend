from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

import aiohttp
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ai_app.ai.dataset import InfluxDataset, DatasetWindow
from ai_app.services.influx_logger import InfluxLogger
from ai_app.core.influxdb_init import get_influx_client
from ai_app.core.demo_time import get_simulated_utc_now
from ai_app.core.ha_ws_listener import fetch_all_homeassistant_states


router = APIRouter(prefix="/influx", tags=["InfluxDB"])


class UserActionLog(BaseModel):
    user_id: int
    entity_id: str
    domain: str
    action: str
    value: Optional[float] = None
    meta: Optional[Dict[str, Any]] = None


@router.get("/health")
async def influx_health():
    try:
        client = await get_influx_client()
        ready = await client.ping()
        return {"ok": bool(ready)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Influx error: {e}")


@router.post("/snapshot")
async def snapshot_homeassistant_states():
    try:
        states = await fetch_all_homeassistant_states()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch HA states: {e}")

    if not isinstance(states, list):
        raise HTTPException(status_code=500, detail="Home Assistant states response is not a list.")

    ts = await get_simulated_utc_now()
    written = 0

    for item in states:
        entity_id = item.get("entity_id")
        if not entity_id or "." not in entity_id:
            continue

        domain = entity_id.split(".", 1)[0]
        state = item.get("state")
        attributes = item.get("attributes", {}) or {}

        await InfluxLogger.log_device_state(
            entity_id=entity_id,
            domain=domain,
            state=state,
            attributes=attributes,
            area=None,
            source="startup_snapshot",
            ts=ts,
        )
        written += 1

    return {"success": True, "written": written, "timestamp_utc": ts.isoformat()}


@router.post("/log-action")
async def log_user_action(payload: UserActionLog):
    await InfluxLogger.log_user_action(
        user_id=payload.user_id,
        entity_id=payload.entity_id,
        domain=payload.domain,
        action=payload.action,
        value=payload.value,
        meta=payload.meta,
        ts=await get_simulated_utc_now(),
    )
    return {"success": True}


@router.get("/history")
async def device_history(
    entity_id: str = Query(...),
    minutes: int = Query(60, ge=1, le=60 * 24 * 30),
    limit: int = Query(200, ge=1, le=2000),
):
    hours = max(1, int((minutes + 59) // 60))
    df = InfluxDataset.fetch_device_state_df(entity_id=entity_id, window=DatasetWindow(hours=hours))

    if df.empty:
        return {"entity_id": entity_id, "rows": []}

    df = df.sort_values("time", ascending=False).head(limit)

    rows = []
    for _, r in df.iterrows():
        rows.append({k: (None if str(v) == "nan" else v) for k, v in r.to_dict().items()})

    return {"entity_id": entity_id, "rows": rows}