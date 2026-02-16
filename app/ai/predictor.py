from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

import pandas as pd

from app.ai.friend_dataset import FriendInfluxDataset
from app.ai.timeseries_builder import BuildConfig, TimeSeriesBuilder
from app.ai.xgb_light_trainer import XGBLightTrainer
from app.ai.xgb_climate_trainer import XGBClimateTrainer
from app.ai.xgb_climate_temp_trainer import XGBClimateTempTrainer


class Predictor:
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

        # Pull last few days for context to build the last row features
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

        now = datetime.now(timezone.utc)

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

        now = datetime.now(timezone.utc)

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

        now = datetime.now(timezone.utc)

        return {
            "ok": True,
            "room": room,
            "domain": "climate",
            "timestamp_utc": now.isoformat(),
            "prediction_horizon_minutes": artifact.cfg.horizon_minutes,
            "predicted_setpoint_celsius": round(pred_setpoint, 2),
        }


