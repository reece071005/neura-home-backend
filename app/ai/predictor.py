from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

import pandas as pd

from app.ai.friend_dataset import FriendInfluxDataset
from app.ai.timeseries_builder import BuildConfig, TimeSeriesBuilder
from app.ai.xgb_light_trainer import XGBLightTrainer


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
