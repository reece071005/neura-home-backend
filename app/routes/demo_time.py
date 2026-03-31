from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app import auth, models
from app.core.demo_time import (
    advance_simulated_time,
    get_clock_payload,
    jump_to_local_time,
    pause_clock,
    reset_demo_clock,
    resume_clock,
    set_demo_enabled,
    set_simulated_local_dubai,
    set_speed,
)


router = APIRouter(prefix="/demo-time", tags=["Demo Time"])


class DemoTimeConfigRequest(BaseModel):
    enabled: Optional[bool] = None
    paused: Optional[bool] = None
    speed: Optional[float] = Field(default=None, gt=0)


class DemoTimeJumpRequest(BaseModel):
    hhmm: str
    keep_date: bool = True


class DemoTimeAdvanceRequest(BaseModel):
    days: int = 0
    hours: int = 0
    minutes: int = 0
    seconds: int = 0


class DemoTimeSetLocalRequest(BaseModel):
    iso_datetime_local_dubai: str


@router.get("")
async def get_demo_time(current_user: models.User = Depends(auth.get_current_active_user)):
    return await get_clock_payload()


@router.post("/config")
async def update_demo_time_config(
    payload: DemoTimeConfigRequest,
    current_admin: models.User = Depends(auth.get_current_admin_user),
):
    if payload.enabled is not None:
        await set_demo_enabled(payload.enabled)

    if payload.speed is not None:
        await set_speed(payload.speed)

    if payload.paused is True:
        await pause_clock()
    elif payload.paused is False:
        await resume_clock()

    return await get_clock_payload()


@router.post("/pause")
async def pause_demo_time(current_admin: models.User = Depends(auth.get_current_admin_user)):
    await pause_clock()
    return await get_clock_payload()


@router.post("/resume")
async def resume_demo_time(current_admin: models.User = Depends(auth.get_current_admin_user)):
    await resume_clock()
    return await get_clock_payload()


@router.post("/jump")
async def jump_demo_time(
    payload: DemoTimeJumpRequest,
    current_admin: models.User = Depends(auth.get_current_admin_user),
):
    await jump_to_local_time(payload.hhmm, keep_date=payload.keep_date)
    return await get_clock_payload()


@router.post("/advance")
async def advance_demo_time(
    payload: DemoTimeAdvanceRequest,
    current_admin: models.User = Depends(auth.get_current_admin_user),
):
    await advance_simulated_time(
        days=payload.days,
        hours=payload.hours,
        minutes=payload.minutes,
        seconds=payload.seconds,
    )
    return await get_clock_payload()


@router.post("/set-local")
async def set_demo_time_local(
    payload: DemoTimeSetLocalRequest,
    current_admin: models.User = Depends(auth.get_current_admin_user),
):
    dt = datetime.fromisoformat(payload.iso_datetime_local_dubai)
    await set_simulated_local_dubai(dt)
    return await get_clock_payload()


@router.post("/reset")
async def reset_demo_time(current_admin: models.User = Depends(auth.get_current_admin_user)):
    await reset_demo_clock()
    return await get_clock_payload()