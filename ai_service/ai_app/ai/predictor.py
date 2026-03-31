from __future__ import annotations

from datetime import datetime, timezone, timedelta, time as dtime
from typing import Any, Dict, List

import pandas as pd

from ai_app.ai.friend_dataset import FriendInfluxDataset
from ai_app.ai.timeseries_builder import BuildConfig, TimeSeriesBuilder
from ai_app.ai.xgb_light_trainer import XGBLightTrainer
from ai_app.ai.xgb_climate_trainer import XGBClimateTrainer
from ai_app.ai.xgb_climate_temp_trainer import XGBClimateTempTrainer
from ai_app.ai.xgb_cover_trainer import XGBCoverTrainer
from ai_app.ai.suggestion_store import SuggestionStore, CooldownConfig
from ai_app.services.room_client import fetch_all_rooms
from ai_app.services.room_config_builder import build_config_from_entities
from ai_app.ai.room_config import ROOM_CONFIG  # fallback

DEFAULT_PRECONDITION = {
    "enabled": True,
    "arrival_time_weekday": "18:30",
    "arrival_time_weekend": "13:00",
    "lead_minutes": 20,
    "min_temp_delta": 1.0,
    "fallback_setpoint": 24.0,
}

async def _get_room_config(room_name: str) -> dict | None:
    """
    1) Try DB-driven rooms via main backend.
    2) If that fails, fallback to ROOM_CONFIG.
    Returns config shaped like:
      {"lights":[], "climate":[], "covers":[], "motion":[], "precondition":{...}}
    """
    # --- try DB first ---
    try:
        rooms = await fetch_all_rooms()
        for r in rooms:
            if str(r.get("name")) == room_name:
                entity_ids = r.get("entity_ids") or []
                cfg = build_config_from_entities(entity_ids)
                # ensure we always have precondition config
                cfg["precondition"] = DEFAULT_PRECONDITION
                return cfg
    except Exception as e:
        print(f"[AI] Failed to fetch rooms from backend: {e}")

    # --- fallback to static config ---
    fallback = ROOM_CONFIG.get(room_name)
    if fallback:
        # ensure fallback also has precondition default if missing
        fb = dict(fallback)
        fb["precondition"] = fb.get("precondition") or DEFAULT_PRECONDITION
        return fb

    return None

def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _local_now_dubai() -> datetime:
    # Dubai is UTC+4 (no DST). Keep explicit so server timezone doesn't matter.
    return datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=4)))


def _parse_hhmm(s: str) -> dtime:
    hh, mm = s.split(":")
    return dtime(hour=int(hh), minute=int(mm))


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

        config = await _get_room_config(room)
        if not config:
            return {"ok": False, "message": "Room not found in DB or fallback config."}

        # ---- Check motion (recent window) ----
        # Motion is still meaningful for lights/covers. Climate is handled separately by arrival preconditioning.
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

        # NOTE: this gate will be applied to lights/covers suggestions only.
        # We'll still compute climate preconditioning even if motion isn't detected.
        suggestions: List[Dict[str, Any]] = []

        # ---- Lights ----
        if not (motion_required and motion_entities and not motion_detected):
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

        # ---- Climate (ARRIVAL PRECONDITIONING) ----
        pre_cfg = (config.get("precondition") or {})
        if bool(pre_cfg.get("enabled", False)):
            now_local = _local_now_dubai()
            is_weekend = now_local.weekday() >= 5

            arrival_str = pre_cfg.get(
                "arrival_time_weekend" if is_weekend else "arrival_time_weekday",
                "18:30",
            )
            lead_minutes = int(pre_cfg.get("lead_minutes", 20))
            min_temp_delta = float(pre_cfg.get("min_temp_delta", 1.0))
            fallback_setpoint = float(pre_cfg.get("fallback_setpoint", 24.0))

            arrival_t = _parse_hhmm(arrival_str)
            arrival_dt = now_local.replace(
                hour=arrival_t.hour, minute=arrival_t.minute, second=0, microsecond=0
            )

            # If arrival already passed today, do nothing.
            if arrival_dt > now_local:
                minutes_to_arrival = (arrival_dt - now_local).total_seconds() / 60.0
                in_window = 0 <= minutes_to_arrival <= lead_minutes

                if in_window:
                    for entity in config.get("climate", []):
                        try:
                            # Cooldown check
                            in_cd = await SuggestionStore.is_in_cooldown(
                                room=room, suggestion_type="climate", entity_id=entity
                            )
                            if in_cd:
                                continue

                            # Desired temperature from model (fallback to config value)
                            setpoint_pred = Predictor.predict_room_climate_setpoint_next_15m(room=entity)
                            desired = setpoint_pred.get("predicted_setpoint_celsius")
                            if desired is None:
                                desired = fallback_setpoint

                            # Current temperature from FRIEND influx
                            current_temp = FriendInfluxDataset.fetch_latest_numeric(
                                entity_id=entity,
                                domain="climate",
                                field="current_temperature",
                                lookback_minutes=60 * 12,
                            )

                            if current_temp is None:
                                continue

                            temp_delta = float(desired) - float(current_temp)

                            # Only act if meaningful gap
                            if abs(temp_delta) < min_temp_delta:
                                continue

                            await SuggestionStore.set_cooldown(
                                room=room,
                                suggestion_type="climate",
                                entity_id=entity,
                                cfg=cooldown_cfg,
                            )

                            suggestions.append({
                                "type": "climate",
                                "entity_id": entity,
                                "confidence": 0.90,
                                "title": "Pre-cool/heat before arrival?",
                                "subtitle": (
                                    f"Arrival at {arrival_str}. "
                                    f"Current {float(current_temp):.1f}°C → target {float(desired):.1f}°C. "
                                    f"Starting now to be comfortable when you enter."
                                ),
                                "arrival_time_local": arrival_str,
                                "minutes_to_arrival": round(float(minutes_to_arrival), 1),
                                "current_temperature": round(float(current_temp), 2),
                                "suggested_setpoint": round(float(desired), 2),
                                "action": {
                                    "domain": "climate",
                                    "service": "set_temperature",
                                    "entity_id": entity,
                                    "temperature": float(desired),
                                }
                            })

                        except Exception:
                            pass

        # ---- Covers ----
        if not (motion_required and motion_entities and not motion_detected):
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