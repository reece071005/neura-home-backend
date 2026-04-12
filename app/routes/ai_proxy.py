from __future__ import annotations

import os
from typing import Any, Dict, Optional

import aiohttp
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator

from app import auth, models


AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://ai_service:8002")

router = APIRouter(prefix="/ai", tags=["AI"])


class ClimatePreferencePayload(BaseModel):
    room: str
    enabled: bool = True
    arrival_time_weekday: str = "18:30"
    arrival_time_weekend: str = "13:00"
    lead_minutes: int = Field(default=30, ge=0, le=180)
    min_temp_delta: float = Field(default=1.0, ge=0.0, le=10.0)
    fallback_setpoint: float = Field(default=24.0, ge=16.0, le=32.0)
    active_confidence_threshold: float = Field(default=0.65, ge=0.0, le=1.0)
    min_setpoint_c: float = Field(default=18.0, ge=10.0, le=35.0)
    max_setpoint_c: float = Field(default=28.0, ge=10.0, le=35.0)

    @field_validator("arrival_time_weekday", "arrival_time_weekend")
    @classmethod
    def validate_hhmm(cls, v: str) -> str:
        parts = v.split(":")
        if len(parts) != 2:
            raise ValueError("Time must be in HH:MM format")

        hh, mm = parts
        hour = int(hh)
        minute = int(mm)

        if hour < 0 or hour > 23 or minute < 0 or minute > 59:
            raise ValueError("Invalid time")

        return f"{hour:02d}:{minute:02d}"

    @field_validator("max_setpoint_c")
    @classmethod
    def validate_max_vs_min(cls, v: float, info):
        min_value = info.data.get("min_setpoint_c", 18.0)
        if v < min_value:
            raise ValueError("max_setpoint_c must be >= min_setpoint_c")
        return v


async def call_ai(
    endpoint: str,
    method: str = "GET",
    params: Optional[Dict[str, Any]] = None,
    json: Optional[Dict[str, Any]] = None,
):
    async with aiohttp.ClientSession() as session:
        async with session.request(
            method,
            f"{AI_SERVICE_URL}{endpoint}",
            params=params,
            json=json,
        ) as resp:
            try:
                data = await resp.json()
            except Exception:
                text = await resp.text()
                raise HTTPException(
                    status_code=resp.status if resp.status >= 400 else 502,
                    detail=f"AI service returned non-JSON response: {text}",
                )

            if resp.status >= 400:
                raise HTTPException(status_code=resp.status, detail=data)

            return data


@router.get("/rooms")
async def rooms(current_user: models.User = Depends(auth.get_current_active_user)):
    return await call_ai("/ai/rooms")


@router.get("/suggestion-cards")
async def suggestion_cards(
    room: str,
    current_user: models.User = Depends(auth.get_current_active_user),
):
    return await call_ai(
        "/ai/suggestion-cards",
        params={"room": room},
    )


@router.get("/smart-suggestions")
async def smart_suggestions(
    room: str,
    current_user: models.User = Depends(auth.get_current_active_user),
):
    return await call_ai(
        "/ai/smart-suggestions",
        params={"room": room},
    )

@router.get("/arrival-preview")
async def arrival_preview(
    room: str,
    current_user: models.User = Depends(auth.get_current_active_user),
):
    return await call_ai(
        "/ai/arrival-preview",
        params={"room": room},
    )

@router.post("/room-ai/preferences")
async def set_room_ai_preferences(
    payload: dict,
    current_user: models.User = Depends(auth.get_current_active_user),
):
    return await call_ai("/ai/room-ai/preferences", method="POST", json=payload)


@router.get("/room-ai/preferences")
async def get_room_ai_preferences(
    room: str,
    current_user: models.User = Depends(auth.get_current_active_user),
):
    return await call_ai(
        "/ai/room-ai/preferences",
        params={"room": room},
    )


@router.delete("/room-ai/preferences")
async def delete_room_ai_preferences(
    room: str,
    current_user: models.User = Depends(auth.get_current_active_user),
):
    return await call_ai(
        "/ai/room-ai/preferences",
        method="DELETE",
        params={"room": room},
    )

@router.post("/climate/preferences")
async def set_climate_preferences(
    payload: dict,
    current_user: models.User = Depends(auth.get_current_active_user),
):
    return await call_ai("/ai/climate/preferences", method="POST", json=payload)


@router.get("/climate/preferences")
async def get_climate_preferences(
    room: str,
    current_user: models.User = Depends(auth.get_current_active_user),
):
    return await call_ai(
        "/ai/climate/preferences",
        params={"room": room},
    )


@router.delete("/climate/preferences")
async def delete_climate_preferences(
    room: str,
    current_user: models.User = Depends(auth.get_current_active_user),
):
    return await call_ai(
        "/ai/climate/preferences",
        method="DELETE",
        params={"room": room},
    )


@router.get("/climate/preconditioning-preview")
async def climate_preconditioning_preview(
    room: str = Query(...),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    return await call_ai(
        "/ai/climate/preconditioning-preview",
        params={"room": room,},
    )


@router.post("/train-room-xgb")
async def train_room(
    room: str,
    days: int = 60,
    current_admin: models.User = Depends(auth.get_current_admin_user),
):
    return await call_ai(
        "/ai/train-room-xgb",
        method="POST",
        params={"room": room, "days": days},
    )


@router.post("/train-climate-xgb")
async def train_climate(
    room: str,
    days: int = 60,
    horizon_minutes: int = 15,
    current_admin: models.User = Depends(auth.get_current_admin_user),
):
    return await call_ai(
        "/ai/train-climate-xgb",
        method="POST",
        params={"room": room, "days": days, "horizon_minutes": horizon_minutes},
    )


@router.post("/train-climate-temp-xgb")
async def train_climate_temp(
    room: str,
    days: int = 60,
    horizon_minutes: int = 15,
    current_admin: models.User = Depends(auth.get_current_admin_user),
):
    return await call_ai(
        "/ai/train-climate-temp-xgb",
        method="POST",
        params={"room": room, "days": days, "horizon_minutes": horizon_minutes},
    )


@router.get("/predict-climate-xgb")
async def predict_climate(
    room: str,
    current_user: models.User = Depends(auth.get_current_active_user),
):
    return await call_ai(
        "/ai/predict-climate-xgb",
        params={"room": room},
    )


@router.get("/predict-climate-temp-xgb")
async def predict_climate_temp(
    room: str,
    current_user: models.User = Depends(auth.get_current_active_user),
):
    return await call_ai(
        "/ai/predict-climate-temp-xgb",
        params={"room": room},
    )

@router.get("/training-readiness")
async def training_readiness(
    room: str,
    min_days: int = 15,
    lookback_days: int = 60,
    current_user: models.User = Depends(auth.get_current_active_user),
):
    return await call_ai(
        "/ai/training-readiness",
        params={
            "room": room,
            "min_days": min_days,
            "lookback_days": lookback_days,
        },
    )


@router.post("/training/preferences")
async def set_training_preferences(
    payload: dict,
    current_user: models.User = Depends(auth.get_current_active_user),
):
    return await call_ai("/ai/training/preferences", method="POST", json=payload)


@router.get("/training/preferences")
async def get_training_preferences(
    room: str,
    current_user: models.User = Depends(auth.get_current_active_user),
):
    return await call_ai(
        "/ai/training/preferences",
        params={"room": room},
    )


@router.delete("/training/preferences")
async def delete_training_preferences(
    room: str,
    current_user: models.User = Depends(auth.get_current_active_user),
):
    return await call_ai(
        "/ai/training/preferences",
        method="DELETE",
        params={"room": room},
    )