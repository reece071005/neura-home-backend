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
class LightModelArtifact:
    room: str
    domain: str
    cfg: BuildConfig
    feature_columns: list[str]
    model: Any
    metrics: dict


class XGBLightTrainer:
    @staticmethod
    def train_room_light(
        *,
        room: str,
        days: int = 60,
        cfg: BuildConfig = BuildConfig(),
    ) -> Dict[str, Any]:

        # 1) Fetch long format from friend influx
        df_long = FriendInfluxDataset.fetch_room_state_df(room=room, days=days)
        if df_long.empty:
            return {"trained": False, "room": room, "message": "No data returned from friend influx."}

        # 2) Filter domain=light
        df_long = df_long[df_long["domain"] == "light"].copy()
        if df_long.empty:
            return {"trained": False, "room": room, "message": "No light data found for this room."}

        # 3) Pivot -> wide
        df_wide = TimeSeriesBuilder.pivot_events_to_wide(df_long)
        if df_wide.empty:
            return {"trained": False, "room": room, "message": "Pivot failed (empty wide dataframe)."}

        # 4) Resample to 5min time grid
        df_ts = TimeSeriesBuilder.resample_room_domain(df_wide, cfg=cfg)

        # 5) Build ML dataset
        df_ml = TimeSeriesBuilder.build_light_classification_dataset(df_ts, cfg=cfg)

        if df_ml.empty or len(df_ml) < cfg.min_rows:
            return {
                "trained": False,
                "room": room,
                "message": f"Not enough training rows after processing. Rows={len(df_ml)} min_required={cfg.min_rows}",
            }

        # 6) Split
        feature_cols = [
            "hour",
            "weekday",
            "is_weekend",
            "state_on",
            "state_on_lag1",
            "brightness",
            "brightness_lag1",
            "brightness_roll_mean_30m",
        ]

        X = df_ml[feature_cols]
        y = df_ml["y_on_future"]

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, shuffle=False
        )

        # 7) Train model
        model = XGBClassifier(
            n_estimators=300,
            max_depth=6,
            learning_rate=0.05,
            subsample=0.9,
            colsample_bytree=0.9,
            eval_metric="logloss",
            random_state=42,
        )

        model.fit(X_train, y_train)

        # 8) Evaluate
        y_pred = model.predict(X_test)
        report = classification_report(y_test, y_pred, output_dict=True)

        artifact = LightModelArtifact(
            room=room,
            domain="light",
            cfg=cfg,
            feature_columns=feature_cols,
            model=model,
            metrics=report,
        )

        XGBLightTrainer._save_artifact(room, artifact)

        return {
            "trained": True,
            "room": room,
            "domain": "light",
            "days": days,
            "rows_raw": int(len(df_long)),
            "rows_ts": int(len(df_ts)),
            "rows_ml": int(len(df_ml)),
            "metrics": report,
            "artifact_path": XGBLightTrainer._artifact_path(room),
        }

    @staticmethod
    def _artifact_path(room: str) -> str:
        os.makedirs(ARTIFACT_DIR, exist_ok=True)
        return os.path.join(ARTIFACT_DIR, f"{room}__light.joblib")

    @staticmethod
    def _save_artifact(room: str, artifact: LightModelArtifact) -> None:
        path = XGBLightTrainer._artifact_path(room)
        joblib.dump(artifact, path)

    @staticmethod
    def load_artifact(room: str) -> Optional[LightModelArtifact]:
        path = XGBLightTrainer._artifact_path(room)
        if not os.path.exists(path):
            return None
        return joblib.load(path)
