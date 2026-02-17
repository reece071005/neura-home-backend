from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import pandas as pd

from app.ai.friend_dataset import FriendInfluxDataset
from app.ai.timeseries_builder import BuildConfig, TimeSeriesBuilder
from app.ai.xgb_light_trainer import XGBLightTrainer
from app.ai.xgb_climate_trainer import XGBClimateTrainer
from app.ai.xgb_climate_temp_trainer import XGBClimateTempTrainer
from app.ai.xgb_cover_trainer import XGBCoverTrainer
from app.ai.room_config import ROOM_CONFIG
from app.ai.suggestion_store import SuggestionStore, CooldownConfig


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Predictor:
    # ==============================
    # Individual model inference
    # ==============================

    @staticmethod
    def predict_room_light_next_15m(
        *,
        room: str,
        days_context: int = 7,
        cfg: BuildConfig = BuildConfig(),
    ) -> Dict[str, Any]:

        artifact = XGBLightTrainer.load_artifact(room)
        if not artifact:
            return {"ok": False, "room": room, "message": "Model not trained. Run /ai/train-room-xgb first."}

        df_long = FriendInfluxDataset.fetch_room_state_df(room=room, days=days_context)
        df_long = df_long[df_long["domain"] == "light"].copy()

        if df_long.empty:
            return {"ok": False, "room": room, "message": "No recent light data for prediction."}

        df_wide = TimeSeriesBuilder.pivot_events_to_wide(df_long)
        df_ts = TimeSeriesBuilder.resample_room_domain(df_wide, cfg=cfg)
        df_ml = TimeSeriesBuilder.build_light_classification_dataset(df_ts, cfg=cfg)

        if df_ml.empty:
            return {"ok": False, "room": room, "message": "Failed to build prediction features."}

        last_row = df_ml.iloc[-1]

        X = pd.DataFrame([last_row[artifact.feature_columns].to_dict()])
        prob_on = float(artifact.model.predict_proba(X)[0][1])

        now = _utc_now()

        return {
            "ok": True,
            "room": room,
            "domain": "light",
            "timestamp_utc": now.isoformat(),
            "prediction_horizon_minutes": artifact.cfg.horizon_minutes,
            "probability_light_on": prob_on,
            "suggest_turn_on": bool(prob_on >= 0.65),
        }

    @staticmethod
    def predict_room_climate_active_next_15m(
        *,
        room: str,
        days_context: int = 7,
        cfg: BuildConfig = BuildConfig(),
    ) -> Dict[str, Any]:

        artifact = XGBClimateTrainer.load_artifact(room)
        if not artifact:
            return {"ok": False, "room": room, "message": "Climate model not trained. Run /ai/train-climate-xgb first."}

        df_long = FriendInfluxDataset.fetch_room_state_df(room=room, days=days_context)
        df_long = df_long[df_long["domain"] == "climate"].copy()

        if df_long.empty:
            return {"ok": False, "room": room, "message": "No recent climate data for prediction."}

        df_wide = TimeSeriesBuilder.pivot_events_to_wide(df_long)
        df_ts = TimeSeriesBuilder.resample_room_domain(df_wide, cfg=cfg)

        keep_cols = ["time", "domain", "entity_id", "hvac_action_str", "current_temperature", "temperature"]
        for c in keep_cols:
            if c not in df_ts.columns:
                df_ts[c] = None
        df_ts = df_ts[keep_cols]

        df_ml = TimeSeriesBuilder.build_climate_classification_dataset(df_ts, cfg=cfg)

        if df_ml.empty:
            return {"ok": False, "room": room, "message": "Failed to build climate prediction features."}

        last_row = df_ml.iloc[-1]
        X = pd.DataFrame([last_row[artifact.feature_columns].to_dict()])

        prob_active = float(artifact.model.predict_proba(X)[0][1])

        now = _utc_now()

        return {
            "ok": True,
            "room": room,
            "domain": "climate",
            "timestamp_utc": now.isoformat(),
            "prediction_horizon_minutes": artifact.cfg.horizon_minutes,
            "probability_climate_active": prob_active,
            "suggest_climate": bool(prob_active >= 0.65),
        }

    @staticmethod
    def predict_room_climate_setpoint_next_15m(
        *,
        room: str,
        days_context: int = 7,
        cfg: BuildConfig = BuildConfig(),
    ) -> Dict[str, Any]:

        artifact = XGBClimateTempTrainer.load_artifact(room)
        if not artifact:
            return {"ok": False, "room": room, "message": "Setpoint model not trained. Run /ai/train-climate-temp-xgb first."}

        df_long = FriendInfluxDataset.fetch_room_state_df(room=room, days=days_context)
        df_long = df_long[df_long["domain"] == "climate"].copy()

        if df_long.empty:
            return {"ok": False, "room": room, "message": "No recent climate data for prediction."}

        df_wide = TimeSeriesBuilder.pivot_events_to_wide(df_long)
        df_ts = TimeSeriesBuilder.resample_room_domain(df_wide, cfg=cfg)

        keep_cols = ["time", "domain", "entity_id", "current_temperature", "temperature"]
        for c in keep_cols:
            if c not in df_ts.columns:
                df_ts[c] = None
        df_ts = df_ts[keep_cols]

        df_ml = TimeSeriesBuilder.build_climate_temperature_regression_dataset(df_ts, cfg=cfg)
        if df_ml.empty:
            return {"ok": False, "room": room, "message": "Failed to build setpoint prediction features."}

        last_row = df_ml.iloc[-1]
        X = pd.DataFrame([last_row[artifact.feature_columns].to_dict()])

        pred_setpoint = float(artifact.model.predict(X)[0])

        now = _utc_now()

        return {
            "ok": True,
            "room": room,
            "domain": "climate",
            "timestamp_utc": now.isoformat(),
            "prediction_horizon_minutes": artifact.cfg.horizon_minutes,
            "predicted_setpoint_celsius": round(pred_setpoint, 2),
        }

    @staticmethod
    def predict_cover_position_next_15m(
        *,
        entity_id: str,
        days_context: int = 7,
        cfg: BuildConfig = BuildConfig(),
    ) -> Dict[str, Any]:

        artifact = XGBCoverTrainer.load_artifact(entity_id)
        if not artifact:
            return {"ok": False, "entity_id": entity_id, "message": "Cover model not trained. Run /ai/train-cover-xgb first."}

        df_long = FriendInfluxDataset.fetch_room_state_df(room=entity_id, days=days_context)
        df_long = df_long[df_long["domain"] == "cover"].copy()
        if df_long.empty:
            return {"ok": False, "entity_id": entity_id, "message": "No recent cover data."}

        df_wide = TimeSeriesBuilder.pivot_events_to_wide(df_long)
        df_ts = TimeSeriesBuilder.resample_room_domain(df_wide, cfg=cfg)

        if "current_position" not in df_ts.columns:
            return {"ok": False, "entity_id": entity_id, "message": "current_position not found."}

        df_ts["current_position"] = pd.to_numeric(df_ts["current_position"], errors="coerce").ffill()
        df_ts = df_ts.dropna(subset=["current_position"])
        if df_ts.empty:
            return {"ok": False, "entity_id": entity_id, "message": "No valid position data."}

        df_ts["hour"] = df_ts["time"].dt.hour
        df_ts["weekday"] = df_ts["time"].dt.weekday
        df_ts["is_weekend"] = (df_ts["weekday"] >= 5).astype(int)
        df_ts["position_lag1"] = df_ts["current_position"].shift(1)
        df_ts["position_roll_mean_30m"] = df_ts["current_position"].rolling(window=6, min_periods=1).mean()

        df_ts = df_ts.dropna(subset=["position_lag1"])
        if df_ts.empty:
            return {"ok": False, "entity_id": entity_id, "message": "Not enough history to form lag features."}

        last = df_ts.iloc[-1]
        X = pd.DataFrame([last[artifact.feature_columns].to_dict()])

        pred_pos = float(artifact.model.predict(X)[0])
        pred_pos = max(0.0, min(100.0, pred_pos))

        now = _utc_now()

        current_pos = float(last["current_position"])
        delta = pred_pos - current_pos

        return {
            "ok": True,
            "entity_id": entity_id,
            "domain": "cover",
            "timestamp_utc": now.isoformat(),
            "prediction_horizon_minutes": artifact.cfg.horizon_minutes,
            "current_position": round(current_pos, 1),
            "predicted_position": round(pred_pos, 1),
            "delta": round(delta, 1),
            "suggest_change": bool(abs(delta) >= 15.0),
        }

    # ==============================
    # Smart suggestion layer (cards)
    # ==============================

    @staticmethod
    async def smart_room_suggestions(
        *,
        room: str,
        motion_required: bool = True,
        cooldown_cfg: CooldownConfig = CooldownConfig(),
    ) -> Dict[str, Any]:

        if room not in ROOM_CONFIG:
            return {"ok": False, "message": "Room not configured."}

        config = ROOM_CONFIG[room]

        # ---- Check motion (recent window) ----
        motion_entities = config.get("motion", []) or []
        motion_detected = False
        motion_details: List[Dict[str, Any]] = []

        for motion_entity in motion_entities:
            try:
                detected = FriendInfluxDataset.fetch_motion_recent(
                    entity_id=motion_entity,
                    minutes=5,
                )
                motion_details.append({
                    "entity_id": motion_entity,
                    "motion_recent_5m": detected
                })

                if detected:
                    motion_detected = True

            except Exception as e:
                motion_details.append({
                    "entity_id": motion_entity,
                    "error": str(e)
                })

        if motion_required and motion_entities and not motion_detected:
            return {
                "ok": True,
                "room": room,
                "motion_detected": False,
                "motion": motion_details,
                "suggestions": [],
            }

        suggestions: List[Dict[str, Any]] = []

        # ---- Lights ----
        for entity in config.get("lights", []):
            try:
                result = Predictor.predict_room_light_next_15m(room=entity)
                if not result.get("suggest_turn_on"):
                    continue

                prob = float(result.get("probability_light_on") or 0.0)
                if prob < 0.65:
                    continue

                # Cooldown check
                in_cd = await SuggestionStore.is_in_cooldown(room=room, suggestion_type="light", entity_id=entity)
                if in_cd:
                    continue

                await SuggestionStore.set_cooldown(
                    room=room,
                    suggestion_type="light",
                    entity_id=entity,
                    cfg=cooldown_cfg,
                )

                suggestions.append({
                    "type": "light",
                    "entity_id": entity,
                    "confidence": prob,
                    "title": "Turn on lights?",
                    "subtitle": f"Predicted you may want lights on soon ({prob:.2f}).",
                    "action": {
                        "domain": "light",
                        "service": "turn_on",
                        "entity_id": entity,
                    }
                })

            except Exception:
                pass

        # ---- Climate ----
        for entity in config.get("climate", []):
            try:
                active = Predictor.predict_room_climate_active_next_15m(room=entity)
                if not active.get("suggest_climate"):
                    continue

                prob = float(active.get("probability_climate_active") or 0.0)
                if prob < 0.65:
                    continue

                # Cooldown check
                in_cd = await SuggestionStore.is_in_cooldown(room=room, suggestion_type="climate", entity_id=entity)
                if in_cd:
                    continue

                setpoint = Predictor.predict_room_climate_setpoint_next_15m(room=entity)
                suggested_temp = setpoint.get("predicted_setpoint_celsius")

                await SuggestionStore.set_cooldown(
                    room=room,
                    suggestion_type="climate",
                    entity_id=entity,
                    cfg=cooldown_cfg,
                )

                suggestions.append({
                    "type": "climate",
                    "entity_id": entity,
                    "confidence": prob,
                    "title": "Adjust AC?",
                    "subtitle": f"Predicted HVAC will be needed soon ({prob:.2f}).",
                    "suggested_setpoint": suggested_temp,
                    "action": {
                        "domain": "climate",
                        "service": "set_temperature",
                        "entity_id": entity,
                        "temperature": suggested_temp,
                    }
                })

            except Exception:
                pass

        # ---- Covers ----
        for entity in config.get("covers", []):
            try:
                result = Predictor.predict_cover_position_next_15m(entity_id=entity)
                if not result.get("suggest_change"):
                    continue

                # Cooldown check
                in_cd = await SuggestionStore.is_in_cooldown(room=room, suggestion_type="cover", entity_id=entity)
                if in_cd:
                    continue

                await SuggestionStore.set_cooldown(
                    room=room,
                    suggestion_type="cover",
                    entity_id=entity,
                    cfg=cooldown_cfg,
                )

                predicted_pos = result.get("predicted_position")

                suggestions.append({
                    "type": "cover",
                    "entity_id": entity,
                    "title": "Adjust blinds?",
                    "subtitle": f"Predicted blind position should change soon.",
                    "predicted_position": predicted_pos,
                    "action": {
                        "domain": "cover",
                        "service": "set_cover_position",
                        "entity_id": entity,
                        "position": predicted_pos,
                    }
                })

            except Exception:
                pass

        return {
            "ok": True,
            "room": room,
            "motion_detected": motion_detected,
            "motion": motion_details,
            "suggestions": suggestions,
        }
