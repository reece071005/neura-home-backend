from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import joblib
import pandas as pd
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

from app.ai.friend_dataset import FriendInfluxDataset
from app.ai.timeseries_builder import BuildConfig, TimeSeriesBuilder


ARTIFACT_DIR = os.getenv("AI_ARTIFACT_DIR_XGB", "app/ai/artifacts/rooms_xgb")


@dataclass
class ClimateModelArtifact:
    room: str
    domain: str
    cfg: BuildConfig
    feature_columns: list[str]
    model: Any
    metrics: dict


class XGBClimateTrainer:
    @staticmethod
    def train_room_climate_active(
        *,
        room: str,
        days: int = 60,
        cfg: BuildConfig = BuildConfig(),
    ) -> Dict[str, Any]:

        df_long = FriendInfluxDataset.fetch_room_state_df(room=room, days=days)
        if df_long.empty:
            return {"trained": False, "room": room, "message": "No data returned from friend influx."}

        df_long = df_long[df_long["domain"] == "climate"].copy()
        if df_long.empty:
            return {"trained": False, "room": room, "message": "No climate data found for this room."}

        df_wide = TimeSeriesBuilder.pivot_events_to_wide(df_long)
        if df_wide.empty:
            return {"trained": False, "room": room, "message": "Pivot failed (empty wide dataframe)."}

        df_ts = TimeSeriesBuilder.resample_room_domain(df_wide, cfg=cfg)

        # Keep only columns we care about for climate
        keep_cols = ["time", "domain", "entity_id", "hvac_action_str", "current_temperature", "temperature"]
        for c in keep_cols:
            if c not in df_ts.columns:
                df_ts[c] = None
        df_ts = df_ts[keep_cols]

        df_ml = TimeSeriesBuilder.build_climate_classification_dataset(df_ts, cfg=cfg)

        if df_ml.empty or len(df_ml) < cfg.min_rows:
            return {
                "trained": False,
                "room": room,
                "message": f"Not enough training rows after processing. Rows={len(df_ml)} min_required={cfg.min_rows}",
            }

        feature_cols = [
            "hour",
            "weekday",
            "is_weekend",
            "hvac_active",
            "hvac_active_lag1",
            "current_temperature",
            "temperature",
            "temp_diff",
            "temp_diff_lag1",
            "current_temp_roll_mean_30m",
        ]

        X = df_ml[feature_cols]
        y = df_ml["y_hvac_active_future"]

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, shuffle=False
        )

        model = XGBClassifier(
            n_estimators=350,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
            eval_metric="logloss",
            random_state=42,
        )

        model.fit(X_train, y_train)

        y_pred = model.predict(X_test)
        report = classification_report(y_test, y_pred, output_dict=True)

        artifact = ClimateModelArtifact(
            room=room,
            domain="climate_active",
            cfg=cfg,
            feature_columns=feature_cols,
            model=model,
            metrics=report,
        )

        XGBClimateTrainer._save_artifact(room, artifact)

        return {
            "trained": True,
            "room": room,
            "domain": "climate",
            "task": "active_prediction",
            "days": days,
            "rows_raw": int(len(df_long)),
            "rows_ts": int(len(df_ts)),
            "rows_ml": int(len(df_ml)),
            "metrics": report,
            "artifact_path": XGBClimateTrainer._artifact_path(room),
        }

    @staticmethod
    def _artifact_path(room: str) -> str:
        os.makedirs(ARTIFACT_DIR, exist_ok=True)
        return os.path.join(ARTIFACT_DIR, f"{room}__climate_active.joblib")

    @staticmethod
    def _save_artifact(room: str, artifact: ClimateModelArtifact) -> None:
        path = XGBClimateTrainer._artifact_path(room)
        joblib.dump(artifact, path)

    @staticmethod
    def load_artifact(room: str) -> Optional[ClimateModelArtifact]:
        path = XGBClimateTrainer._artifact_path(room)
        if not os.path.exists(path):
            return None
        return joblib.load(path)
