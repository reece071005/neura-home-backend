from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import joblib
import pandas as pd
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.model_selection import train_test_split
from xgboost import XGBRegressor

from ai_app.ai.friend_dataset import FriendInfluxDataset
from ai_app.ai.timeseries_builder import BuildConfig, TimeSeriesBuilder


ARTIFACT_DIR = os.getenv("AI_ARTIFACT_DIR_XGB", "ai_app/ai/artifacts/rooms_xgb")


@dataclass
class ClimateTempModelArtifact:
    room: str
    domain: str
    cfg: BuildConfig
    feature_columns: list[str]
    model: Any
    metrics: dict


class XGBClimateTempTrainer:
    @staticmethod
    def train_room_climate_setpoint(
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

        keep_cols = ["time", "domain", "entity_id", "current_temperature", "temperature"]
        for c in keep_cols:
            if c not in df_ts.columns:
                df_ts[c] = None
        df_ts = df_ts[keep_cols]

        df_ml = TimeSeriesBuilder.build_climate_temperature_regression_dataset(df_ts, cfg=cfg)

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
            "current_temperature",
            "temperature",
            "temp_diff",
            "setpoint_lag1",
            "current_temp_lag1",
            "temp_diff_lag1",
            "current_temp_roll_mean_30m",
        ]

        X = df_ml[feature_cols]
        y = df_ml["y_setpoint_future"]

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, shuffle=False
        )

        model = XGBRegressor(
            n_estimators=400,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
            objective="reg:squarederror",
            random_state=42,
        )

        model.fit(X_train, y_train)

        y_pred = model.predict(X_test)

        mae = float(mean_absolute_error(y_test, y_pred))
        mse = float(mean_squared_error(y_test, y_pred))
        rmse = mse ** 0.5

        metrics = {
            "mae": mae,
            "rmse": rmse,
            "y_test_mean": float(y_test.mean()),
            "y_test_std": float(y_test.std()),
        }

        artifact = ClimateTempModelArtifact(
            room=room,
            domain="climate_setpoint",
            cfg=cfg,
            feature_columns=feature_cols,
            model=model,
            metrics=metrics,
        )

        XGBClimateTempTrainer._save_artifact(room, artifact)

        return {
            "trained": True,
            "room": room,
            "domain": "climate",
            "task": "setpoint_regression",
            "days": days,
            "rows_raw": int(len(df_long)),
            "rows_ts": int(len(df_ts)),
            "rows_ml": int(len(df_ml)),
            "metrics": metrics,
            "artifact_path": XGBClimateTempTrainer._artifact_path(room),
        }

    @staticmethod
    def _artifact_path(room: str) -> str:
        os.makedirs(ARTIFACT_DIR, exist_ok=True)
        return os.path.join(ARTIFACT_DIR, f"{room}__climate_setpoint.joblib")

    @staticmethod
    def _save_artifact(room: str, artifact: ClimateTempModelArtifact) -> None:
        path = XGBClimateTempTrainer._artifact_path(room)
        joblib.dump(artifact, path)

    @staticmethod
    def load_artifact(room: str) -> Optional[ClimateTempModelArtifact]:
        path = XGBClimateTempTrainer._artifact_path(room)
        if not os.path.exists(path):
            return None
        return joblib.load(path)
