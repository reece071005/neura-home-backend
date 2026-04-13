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
class CoverModelArtifact:
    entity_id: str
    cfg: BuildConfig
    feature_columns: list[str]
    model: Any
    metrics: dict


class XGBCoverTrainer:
    @staticmethod
    def train_cover_position(
        *,
        entity_id: str,
        days: int = 60,
        cfg: BuildConfig = BuildConfig(),
    ) -> Dict[str, Any]:

        df_long = FriendInfluxDataset.fetch_room_state_df(room=entity_id, days=days)
        if df_long.empty:
            return {"trained": False, "entity_id": entity_id, "message": "No data returned."}

        df_long = df_long[df_long["domain"] == "cover"].copy()
        if df_long.empty:
            return {"trained": False, "entity_id": entity_id, "message": "No cover data found."}

        df_wide = TimeSeriesBuilder.pivot_events_to_wide(df_long)
        if df_wide.empty:
            return {"trained": False, "entity_id": entity_id, "message": "Pivot failed."}

        df_ts = TimeSeriesBuilder.resample_room_domain(df_wide, cfg=cfg)

        if "current_position" not in df_ts.columns:
            return {"trained": False, "entity_id": entity_id, "message": "current_position not found."}

        df_ts["current_position"] = pd.to_numeric(df_ts["current_position"], errors="coerce")
        df_ts["current_position"] = df_ts["current_position"].ffill()

        df_ts = df_ts.dropna(subset=["current_position"])
        if df_ts.empty:
            return {"trained": False, "entity_id": entity_id, "message": "No valid position data."}


        df_ts["hour"] = df_ts["time"].dt.hour
        df_ts["weekday"] = df_ts["time"].dt.weekday
        df_ts["is_weekend"] = (df_ts["weekday"] >= 5).astype(int)


        df_ts["position_lag1"] = df_ts["current_position"].shift(1)
        df_ts["position_roll_mean_30m"] = df_ts["current_position"].rolling(window=6, min_periods=1).mean()


        step_minutes = int(pd.Timedelta(cfg.freq).total_seconds() // 60)
        horizon_steps = max(1, cfg.horizon_minutes // step_minutes)

        df_ts["y_position_future"] = df_ts["current_position"].shift(-horizon_steps)

        df_ml = df_ts.dropna(subset=["position_lag1", "y_position_future"])

        if df_ml.empty or len(df_ml) < cfg.min_rows:
            return {
                "trained": False,
                "entity_id": entity_id,
                "message": f"Not enough training rows. Rows={len(df_ml)}"
            }

        feature_cols = [
            "hour",
            "weekday",
            "is_weekend",
            "current_position",
            "position_lag1",
            "position_roll_mean_30m",
        ]

        X = df_ml[feature_cols]
        y = df_ml["y_position_future"]

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, shuffle=False
        )

        model = XGBRegressor(
            n_estimators=300,
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

        artifact = CoverModelArtifact(
            entity_id=entity_id,
            cfg=cfg,
            feature_columns=feature_cols,
            model=model,
            metrics=metrics,
        )

        path = os.path.join(ARTIFACT_DIR, f"{entity_id}__cover_position.joblib")
        os.makedirs(ARTIFACT_DIR, exist_ok=True)
        joblib.dump(artifact, path)

        return {
            "trained": True,
            "entity_id": entity_id,
            "task": "cover_position_regression",
            "days": days,
            "rows_ml": int(len(df_ml)),
            "metrics": metrics,
            "artifact_path": path,
        }

    @staticmethod
    def load_artifact(entity_id: str) -> Optional[CoverModelArtifact]:
        path = os.path.join(ARTIFACT_DIR, f"{entity_id}__cover_position.joblib")
        if not os.path.exists(path):
            return None
        return joblib.load(path)
