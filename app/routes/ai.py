from __future__ import annotations

from typing import Any, Dict, Optional, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app import auth, models
from app.ai.room_trainer import RoomTrainer
from app.ai.timeseries_builder import BuildConfig
from app.ai.xgb_light_trainer import XGBLightTrainer
from app.ai.predictor import Predictor
from app.ai.xgb_climate_trainer import XGBClimateTrainer
from app.ai.xgb_climate_temp_trainer import XGBClimateTempTrainer
from app.ai.xgb_cover_trainer import XGBCoverTrainer
from app.ai.room_config import ROOM_CONFIG
from app.ai.suggestion_store import SuggestionStore


router = APIRouter(prefix="/ai", tags=["AI"])


# ============================================
# Frontend-friendly models
# ============================================

SuggestionType = Literal["light", "climate", "cover"]
FeedbackDecision = Literal["accepted", "declined", "dismissed"]


class SuggestionFeedback(BaseModel):
    room: str = Field(..., description="Room key from ROOM_CONFIG")
    type: SuggestionType
    entity_id: str
    decision: FeedbackDecision
    meta: Optional[Dict[str, Any]] = None


# ============================================
# NEW: Frontend endpoints
# ============================================

@router.get("/rooms")
async def list_rooms(
    current_user: models.User = Depends(auth.get_current_active_user),
):
    rooms = []
    for room, cfg in ROOM_CONFIG.items():
        rooms.append({
            "room": room,
            "lights": cfg.get("lights", []),
            "climate": cfg.get("climate", []),
            "covers": cfg.get("covers", []),
            "motion": cfg.get("motion", []),
        })

    return {"ok": True, "rooms": rooms}


@router.get("/suggestion-cards")
async def suggestion_cards(
    room: str = Query(...),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """
    Frontend endpoint:
    - applies motion gate
    - applies cooldown
    - returns suggestion cards
    """
    return await Predictor.smart_room_suggestions(room=room, motion_required=True)


@router.post("/suggestion-feedback")
async def suggestion_feedback(
    payload: SuggestionFeedback,
    current_user: models.User = Depends(auth.get_current_active_user),
):
    await SuggestionStore.log_feedback(
        user_id=current_user.id,
        room=payload.room,
        suggestion_type=payload.type,
        entity_id=payload.entity_id,
        decision=payload.decision,
        meta=payload.meta,
    )
    return {"ok": True}


# ============================================
# OLD (probability profile baseline)
# ============================================

@router.post("/train-room")
async def train_room(
    room: str = Query(..., description="Room entity_id like living_room"),
    days: int = Query(60, ge=1, le=365),
    current_admin: models.User = Depends(auth.get_current_admin_user),
):
    return RoomTrainer.train_room(room=room, days=days)


@router.get("/predict-room")
async def predict_room(
    room: str = Query(...),
    hour: int = Query(..., ge=0, le=23),
    threshold: float = Query(0.25, ge=0.0, le=1.0),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    from datetime import datetime

    now = datetime.utcnow()
    is_weekend = now.weekday() >= 5
    day_type = "weekend" if is_weekend else "weekday"

    domains_to_check = ["light", "climate", "cover", "fan"]
    actions = []

    for domain in domains_to_check:
        profile = RoomTrainer.load_profile(room=room, domain=domain)
        if not profile:
            continue

        section = profile.get(day_type, {})
        probs = section.get("turn_on_probability", {})

        conf = float(probs.get(hour, 0.0))
        if conf < threshold:
            continue

        action = {
            "domain": domain,
            "action": "turn_on",
            "confidence": conf,
            "day_type": day_type,
        }

        if domain == "light":
            avg_b = section.get("avg_brightness", {})
            if hour in avg_b:
                action["brightness"] = avg_b[hour]

        actions.append(action)

    return {
        "room": room,
        "hour": hour,
        "day_type": day_type,
        "actions": actions,
    }


# ============================================
# NEW (real ML using XGBoost)
# ============================================

@router.post("/train-room-xgb")
async def train_room_xgb_light(
    room: str = Query(..., description="Room entity_id like living_room"),
    days: int = Query(60, ge=7, le=365),
    horizon_minutes: int = Query(15, ge=5, le=60),
    current_admin: models.User = Depends(auth.get_current_admin_user),
):
    cfg = BuildConfig(freq="5min", horizon_minutes=horizon_minutes)
    return XGBLightTrainer.train_room_light(room=room, days=days, cfg=cfg)


@router.get("/predict-room-xgb")
async def predict_room_xgb_light(
    room: str = Query(...),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    cfg = BuildConfig(freq="5min", horizon_minutes=15)
    return Predictor.predict_room_light_next_15m(room=room, days_context=7, cfg=cfg)


@router.post("/train-climate-xgb")
async def train_room_xgb_climate(
    room: str = Query(...),
    days: int = Query(60, ge=7, le=365),
    horizon_minutes: int = Query(15, ge=5, le=60),
    current_admin: models.User = Depends(auth.get_current_admin_user),
):
    cfg = BuildConfig(freq="5min", horizon_minutes=horizon_minutes)
    return XGBClimateTrainer.train_room_climate_active(room=room, days=days, cfg=cfg)


@router.get("/predict-climate-xgb")
async def predict_room_xgb_climate(
    room: str = Query(...),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    cfg = BuildConfig(freq="5min", horizon_minutes=15)
    return Predictor.predict_room_climate_active_next_15m(room=room, days_context=7, cfg=cfg)


@router.post("/train-climate-temp-xgb")
async def train_room_xgb_climate_temp(
    room: str = Query(...),
    days: int = Query(60, ge=7, le=365),
    horizon_minutes: int = Query(15, ge=5, le=60),
    current_admin: models.User = Depends(auth.get_current_admin_user),
):
    cfg = BuildConfig(freq="5min", horizon_minutes=horizon_minutes)
    return XGBClimateTempTrainer.train_room_climate_setpoint(room=room, days=days, cfg=cfg)


@router.get("/predict-climate-temp-xgb")
async def predict_room_xgb_climate_temp(
    room: str = Query(...),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    cfg = BuildConfig(freq="5min", horizon_minutes=15)
    return Predictor.predict_room_climate_setpoint_next_15m(room=room, days_context=7, cfg=cfg)


@router.post("/train-cover-xgb")
async def train_cover_xgb(
    entity_id: str = Query(..., description="Cover entity_id like reece_s_window_blind"),
    days: int = Query(60, ge=7, le=365),
    horizon_minutes: int = Query(15, ge=5, le=60),
    current_admin: models.User = Depends(auth.get_current_admin_user),
):
    cfg = BuildConfig(freq="5min", horizon_minutes=horizon_minutes)
    return XGBCoverTrainer.train_cover_position(entity_id=entity_id, days=days, cfg=cfg)


@router.get("/predict-cover-xgb")
async def predict_cover_xgb(
    entity_id: str = Query(...),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    cfg = BuildConfig(freq="5min", horizon_minutes=15)
    return Predictor.predict_cover_position_next_15m(entity_id=entity_id, days_context=7, cfg=cfg)


# Keep your original endpoint name for backwards compatibility
@router.get("/smart-suggestions")
async def smart_suggestions(
    room: str = Query(...),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    return await Predictor.smart_room_suggestions(room=room)
