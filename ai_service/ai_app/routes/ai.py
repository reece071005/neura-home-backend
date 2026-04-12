from __future__ import annotations

from typing import Any, Dict, Optional, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field, field_validator

from ai_app.ai.room_trainer import RoomTrainer
from ai_app.ai.timeseries_builder import BuildConfig
from ai_app.ai.xgb_light_trainer import XGBLightTrainer
from ai_app.ai.predictor import Predictor
from ai_app.ai.xgb_climate_trainer import XGBClimateTrainer
from ai_app.ai.xgb_climate_temp_trainer import XGBClimateTempTrainer
from ai_app.ai.xgb_cover_trainer import XGBCoverTrainer
from ai_app.ai.room_config import ROOM_CONFIG
from ai_app.ai.suggestion_store import SuggestionStore
from ai_app.ai.user_preference_store import UserPreferenceStore, ClimatePreference
from ai_app.core.demo_time import get_simulated_local_now_dubai
from ai_app.ai.dataset import InfluxDataset, DatasetWindow
from ai_app.services.room_client import fetch_all_rooms
from ai_app.ai.room_ai_preference_store import RoomAIPreferenceStore
from ai_app.ai.training_preference_store import TrainingPreferenceStore
router = APIRouter(prefix="/ai", tags=["AI"])

SuggestionType = Literal["light", "climate", "cover"]
FeedbackDecision = Literal["accepted", "declined", "dismissed"]


class SuggestionFeedback(BaseModel):
    room: str
    type: SuggestionType
    entity_id: str
    decision: FeedbackDecision
    meta: Optional[Dict[str, Any]] = None

class RoomAIPreferencePayload(BaseModel):
    room: str
    enabled: bool


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


class TrainingPreferencePayload(BaseModel):
    room: str
    enabled: bool = True
    frequency: Literal[ "daily", "weekly", "monthly"] = "weekly"


def _normalize_room_name(value: str) -> str:
    return value.strip().lower()


def _find_room_by_name(rooms: list[dict], room: str) -> dict | None:
    requested_room = _normalize_room_name(room)

    for r in rooms:
        room_name = _normalize_room_name(str(r.get("name", "")))
        if room_name == requested_room:
            return r

    return None


@router.get("/rooms")
async def list_rooms():
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
):
    return await Predictor.smart_room_suggestions(room=room, motion_required=True)


@router.post("/suggestion-feedback")
async def suggestion_feedback(payload: SuggestionFeedback):
    await SuggestionStore.log_feedback(
        user_id=0,
        room=payload.room,
        suggestion_type=payload.type,
        entity_id=payload.entity_id,
        decision=payload.decision,
        meta=payload.meta,
    )
    return {"ok": True}


@router.get("/smart-suggestions")
async def smart_suggestions(
    room: str = Query(...),
):
    return await Predictor.smart_room_suggestions(room=room)

@router.get("/arrival-preview")
async def arrival_preview(
    room: str = Query(...),
):
    result = await Predictor.smart_room_suggestions(
        room=room,
        motion_required=False,
    )

    return {
        "ok": True,
        "room": room,
        "preview": True,
        "suggestions": result.get("suggestions", []),
        "precondition_config_used": result.get("precondition_config_used"),
    }

@router.post("/room-ai/preferences")
async def set_room_ai_preferences(payload: RoomAIPreferencePayload):
    saved = await RoomAIPreferenceStore.set_room_ai_enabled(
        room=payload.room,
        enabled=payload.enabled,
    )

    return {
        "ok": True,
        "room": payload.room,
        "preferences": saved,
    }


@router.get("/room-ai/preferences")
async def get_room_ai_preferences(
    room: str = Query(...),
):
    saved = await RoomAIPreferenceStore.get_room_ai_enabled(room=room)

    try:
        rooms = await fetch_all_rooms()
    except Exception:
        rooms = []

    room_obj = _find_room_by_name(rooms, room)
    requested_room = room.strip().lower()
    for r in rooms:
        room_name = str(r.get("name", "")).strip().lower()
        if room_name == requested_room:
            room_obj = r
            break

    has_motion_sensor = False
    if room_obj:
        entity_ids = room_obj.get("entity_ids") or []
        has_motion_sensor = any(
            str(e).startswith("binary_sensor.") and any(
                keyword in str(e).lower()
                for keyword in ["occupancy", "motion", "presence"]
            )
            for e in entity_ids
        )

    default_enabled = has_motion_sensor

    if not saved:
        return {
            "ok": True,
            "room": room,
            "preferences": {
                "enabled": default_enabled
            },
            "defaulted": True,
            "has_motion_sensor": has_motion_sensor,
            "message": "No saved room AI preference. Using default based on sensor availability.",
        }

    return {
        "ok": True,
        "room": room,
        "preferences": saved,
        "defaulted": False,
        "has_motion_sensor": has_motion_sensor,
    }


@router.delete("/room-ai/preferences")
async def delete_room_ai_preferences(
    room: str = Query(...),
):
    deleted = await RoomAIPreferenceStore.delete_room_ai_enabled(room=room)
    return {
        "ok": True,
        "room": room,
        "deleted": deleted,
    }

@router.post("/climate/preferences")
async def set_climate_preferences(payload: ClimatePreferencePayload):
    prefs = ClimatePreference(
        enabled=payload.enabled,
        arrival_time_weekday=payload.arrival_time_weekday,
        arrival_time_weekend=payload.arrival_time_weekend,
        lead_minutes=payload.lead_minutes,
        min_temp_delta=payload.min_temp_delta,
        fallback_setpoint=payload.fallback_setpoint,
        active_confidence_threshold=payload.active_confidence_threshold,
        min_setpoint_c=payload.min_setpoint_c,
        max_setpoint_c=payload.max_setpoint_c,
    )

    saved = await UserPreferenceStore.set_climate_preferences(
        room=payload.room,
        preferences=prefs,
    )

    return {
        "ok": True,
        "room": payload.room,
        "preferences": saved,
    }

@router.get("/climate/preferences")
async def get_climate_preferences(
    room: str = Query(...),
):
    saved = await UserPreferenceStore.get_climate_preferences(room=room)

    if not saved:
        return {
            "ok": True,
            "room": room,
            "preferences": None,
            "message": "No saved climate preferences for this room.",
        }

    return {
        "ok": True,
        "room": room,
        "preferences": saved,
    }

@router.delete("/climate/preferences")
async def delete_climate_preferences(
    room: str = Query(...),
):
    deleted = await UserPreferenceStore.delete_climate_preferences(room=room)
    return {
        "ok": True,
        "room": room,
        "deleted": deleted,
    }


@router.get("/climate/preconditioning-preview")
async def climate_preconditioning_preview(
    room: str = Query(...),
):
    result = await Predictor.smart_room_suggestions(room=room)

    climate_suggestions = [
        s for s in result.get("suggestions", [])
        if s.get("type") == "climate"
    ]

    return {
        "ok": True,
        "room": room,
        "precondition_config_used": result.get("precondition_config_used"),
        "climate_suggestions": climate_suggestions,
    }


@router.post("/train-room")
async def train_room(room: str, days: int = 60):
    return RoomTrainer.train_room(room=room, days=days)


@router.get("/predict-room")
async def predict_room(room: str, hour: int, threshold: float = 0.25):
    now = await get_simulated_local_now_dubai()
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


@router.post("/train-room-xgb")
async def train_room_xgb_light(room: str, days: int = 60, horizon_minutes: int = 15):
    cfg = BuildConfig(freq="5min", horizon_minutes=horizon_minutes)
    return XGBLightTrainer.train_room_light(room=room, days=days, cfg=cfg)


@router.get("/predict-room-xgb")
async def predict_room_xgb_light(room: str):
    cfg = BuildConfig(freq="5min", horizon_minutes=15)
    return await Predictor.predict_room_light_next_15m(room=room, days_context=7, cfg=cfg)


@router.post("/train-climate-xgb")
async def train_room_xgb_climate(room: str, days: int = 60, horizon_minutes: int = 15):
    cfg = BuildConfig(freq="5min", horizon_minutes=horizon_minutes)
    return XGBClimateTrainer.train_room_climate_active(room=room, days=days, cfg=cfg)


@router.get("/predict-climate-xgb")
async def predict_room_xgb_climate(room: str):
    cfg = BuildConfig(freq="5min", horizon_minutes=15)
    return await Predictor.predict_room_climate_active_next_15m(room=room, days_context=7, cfg=cfg)


@router.post("/train-climate-temp-xgb")
async def train_room_xgb_climate_temp(room: str, days: int = 60, horizon_minutes: int = 15):
    cfg = BuildConfig(freq="5min", horizon_minutes=horizon_minutes)
    return XGBClimateTempTrainer.train_room_climate_setpoint(room=room, days=days, cfg=cfg)


@router.get("/predict-climate-temp-xgb")
async def predict_room_xgb_climate_temp(room: str):
    cfg = BuildConfig(freq="5min", horizon_minutes=15)
    return await Predictor.predict_room_climate_setpoint_next_15m(room=room, days_context=7, cfg=cfg)


@router.post("/train-cover-xgb")
async def train_cover_xgb(entity_id: str, days: int = 60, horizon_minutes: int = 15):
    cfg = BuildConfig(freq="5min", horizon_minutes=horizon_minutes)
    return XGBCoverTrainer.train_cover_position(entity_id=entity_id, days=days, cfg=cfg)


@router.get("/predict-cover-xgb")
async def predict_cover_xgb(entity_id: str):
    cfg = BuildConfig(freq="5min", horizon_minutes=15)
    return await Predictor.predict_cover_position_next_15m(entity_id=entity_id, days_context=7, cfg=cfg)


@router.get("/training-readiness")
async def training_readiness(room: str, min_days: int = 15, lookback_days: int = 60):
    try:
        rooms = await fetch_all_rooms()
    except Exception as e:
        return {
            "ok": False,
            "room": room,
            "ready": False,
            "message": f"Failed to fetch rooms: {e}",
        }

    room_obj = _find_room_by_name(rooms, room)
    requested_room = room.strip().lower()
    for r in rooms:
        room_name = str(r.get("name", "")).strip().lower()
        if room_name == requested_room:
            room_obj = r
            break

    if not room_obj:
        return {
            "ok": False,
            "room": room,
            "ready": False,
            "message": "Room not found.",
        }

    entity_ids = room_obj.get("entity_ids") or []
    if not entity_ids:
        return {
            "ok": True,
            "room": room,
            "ready": False,
            "days_available": 0,
            "min_days_required": min_days,
            "message": "Room has no configured devices.",
        }

    try:
        df = InfluxDataset.fetch_room_device_state_df(
            entity_ids=entity_ids,
            window=DatasetWindow(hours=lookback_days * 24),
        )
    except Exception as e:
        return {
            "ok": False,
            "room": room,
            "ready": False,
            "message": f"Failed to read Influx data: {e}",
        }

    if df.empty or "time" not in df.columns:
        return {
            "ok": True,
            "room": room,
            "ready": False,
            "days_available": 0,
            "min_days_required": min_days,
            "message": "No historical device data found yet.",
        }

    min_time = df["time"].min()
    max_time = df["time"].max()

    if min_time is None or max_time is None:
        return {
            "ok": True,
            "room": room,
            "ready": False,
            "days_available": 0,
            "min_days_required": min_days,
            "message": "No valid timestamps found in historical data.",
        }

    days_available = max(0, (max_time - min_time).days)
    ready = days_available >= min_days

    return {
        "ok": True,
        "room": room,
        "ready": ready,
        "days_available": days_available,
        "min_days_required": min_days,
        "data_points": int(len(df)),
        "first_seen_utc": min_time.isoformat(),
        "last_seen_utc": max_time.isoformat(),
        "message": (
            "Enough historical data is available for training."
            if ready
            else "Not enough historical data yet."
        ),
    }

@router.post("/training/preferences")
async def set_training_preferences(payload: TrainingPreferencePayload):
    saved = await TrainingPreferenceStore.set_training_preferences(
        room=payload.room,
        enabled=payload.enabled,
        frequency=payload.frequency,
    )

    return {
        "ok": True,
        "room": payload.room,
        "preferences": saved,
    }


@router.get("/training/preferences")
async def get_training_preferences(
    room: str = Query(...),
):
    saved = await TrainingPreferenceStore.get_training_preferences(room=room)

    if not saved:
        return {
            "ok": True,
            "room": room,
            "preferences": {
                "enabled": True,
                "frequency": "manual",
                "last_trained_at": None,
            },
            "defaulted": True,
            "message": "No saved training preferences for this room.",
        }

    return {
        "ok": True,
        "room": room,
        "preferences": saved,
        "defaulted": False,
    }


@router.delete("/training/preferences")
async def delete_training_preferences(
    room: str = Query(...),
):
    deleted = await TrainingPreferenceStore.delete_training_preferences(room=room)
    return {
        "ok": True,
        "room": room,
        "deleted": deleted,
    }