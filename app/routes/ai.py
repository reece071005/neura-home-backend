from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from app import auth, models

from app.ai.room_trainer import RoomTrainer
from app.ai.timeseries_builder import BuildConfig
from app.ai.xgb_light_trainer import XGBLightTrainer
from app.ai.predictor import Predictor
from app.ai.xgb_climate_trainer import XGBClimateTrainer
from app.ai.xgb_climate_temp_trainer import XGBClimateTempTrainer


router = APIRouter(prefix="/ai", tags=["AI"])


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

