from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from app.core.influxdb_init import get_influx_client
from app.services.influx_logger import InfluxLogger
from app.core.homeassistant import DeviceControl
from app import auth, models

from app.services.influx_dataset import InfluxDataset, DatasetWindow


router = APIRouter(prefix="/influx", tags=["InfluxDB"])


class UserActionLog(BaseModel):
    entity_id: str
    domain: str
    action: str
    value: Optional[float] = None
    meta: Optional[Dict[str, Any]] = None


@router.get("/health")
async def influx_health(
    current_user: models.User = Depends(auth.get_current_active_user),
):
    try:
        client = get_influx_client()
        ready = client.ping()
        return {"ok": bool(ready)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Influx error: {e}")


@router.post("/snapshot")
async def snapshot_homeassistant_states(
    current_user: models.User = Depends(auth.get_current_active_user),
):
    states = await DeviceControl.get_current_state()
    if not isinstance(states, list):
        raise HTTPException(status_code=500, detail="Home Assistant states response is not a list.")

    ts = datetime.now(timezone.utc)
    written = 0

    for item in states:
        entity_id = item.get("entity_id")
        if not entity_id or "." not in entity_id:
            continue

        domain = entity_id.split(".", 1)[0]
        state = item.get("state")
        attributes = item.get("attributes", {}) or {}

        InfluxLogger.log_device_state(
            entity_id=entity_id,
            domain=domain,
            state=state,
            attributes=attributes,
            area=None,
            source="snapshot",
            ts=ts,
        )
        written += 1

    return {"success": True, "written": written, "timestamp_utc": ts.isoformat()}


@router.post("/log-action")
async def log_user_action(
    payload: UserActionLog,
    current_user: models.User = Depends(auth.get_current_active_user),
):
    InfluxLogger.log_user_action(
        user_id=current_user.id,
        entity_id=payload.entity_id,
        domain=payload.domain,
        action=payload.action,
        value=payload.value,
        meta=payload.meta,
        ts=datetime.now(timezone.utc),
    )
    return {"success": True}


@router.get("/history")
async def device_history(
    entity_id: str = Query(...),
    minutes: int = Query(60, ge=1, le=60 * 24 * 30),
    limit: int = Query(200, ge=1, le=2000),
    current_user: models.User = Depends(auth.get_current_active_user),
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
