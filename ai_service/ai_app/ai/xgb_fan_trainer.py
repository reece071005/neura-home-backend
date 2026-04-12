from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

import joblib
import pandas as pd
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

from ai_app.ai.friend_dataset import FriendInfluxDataset
from ai_app.ai.timeseries_builder import BuildConfig, TimeSeriesBuilder


ARTIFACT_DIR = os.getenv("AI_ARTIFACT_DIR_XGB", "ai_app/ai/artifacts/rooms_xgb")


@dataclass
class FanModelArtifact:
    room: str
    domain: str
    cfg: BuildConfig
    feature_columns: list[str]
    model: Any
    metrics: dict
    fan_entity_id: Optional[str] = None
    climate_entity_id: Optional[str] = None


class XGBFanTrainer:
    @staticmethod
    def train_room_fan(
        *,
        room: str,
        days: int = 60,
        cfg: BuildConfig = BuildConfig(),
    ) -> Dict[str, Any]:
        df_long = FriendInfluxDataset.fetch_room_state_df(room=room, days=days)
        if df_long.empty:
            return {
                "trained": False,
                "room": room,
                "message": "No data returned from friend influx.",
            }

        fan_df = df_long[df_long["domain"] == "fan"].copy()
        climate_df = df_long[df_long["domain"] == "climate"].copy()

        if fan_df.empty:
            return {
                "trained": False,
                "room": room,
                "message": "No fan data found for this room.",
            }

        # Pick first fan entity in room for now
        fan_entity_ids = fan_df["entity_id"].dropna().unique().tolist()
        fan_entity_id = str(fan_entity_ids[0]) if fan_entity_ids else None
        if not fan_entity_id:
            return {
                "trained": False,
                "room": room,
                "message": "Could not determine fan entity_id.",
            }

        fan_df = fan_df[fan_df["entity_id"] == fan_entity_id].copy()

        climate_entity_id = None
        if not climate_df.empty:
            climate_entity_ids = climate_df["entity_id"].dropna().unique().tolist()
            if climate_entity_ids:
                climate_entity_id = str(climate_entity_ids[0])
                climate_df = climate_df[climate_df["entity_id"] == climate_entity_id].copy()

        fan_wide = TimeSeriesBuilder.pivot_events_to_wide(fan_df)
        if fan_wide.empty:
            return {
                "trained": False,
                "room": room,
                "message": "Fan pivot failed (empty wide dataframe).",
            }

        fan_ts = TimeSeriesBuilder.resample_room_domain(fan_wide, cfg=cfg)
        if fan_ts.empty:
            return {
                "trained": False,
                "room": room,
                "message": "Fan resampling produced no usable rows.",
            }

        climate_ts = pd.DataFrame()
        if climate_entity_id and not climate_df.empty:
            climate_wide = TimeSeriesBuilder.pivot_events_to_wide(climate_df)
            if not climate_wide.empty:
                climate_ts = TimeSeriesBuilder.resample_room_domain(climate_wide, cfg=cfg)

        df_ml = TimeSeriesBuilder.build_fan_classification_dataset(
            fan_ts=fan_ts,
            climate_ts=climate_ts,
            cfg=cfg,
        )

        if df_ml.empty or len(df_ml) < cfg.min_rows:
            return {
                "trained": False,
                "room": room,
                "message": (
                    f"Not enough fan training rows after processing. "
                    f"Rows={len(df_ml)} min_required={cfg.min_rows}"
                ),
                "fan_entity_id": fan_entity_id,
                "climate_entity_id": climate_entity_id,
            }

        feature_cols = [
            "hour",
            "weekday",
            "is_weekend",
            "fan_state_on",
            "fan_state_on_lag1",
            "fan_percentage",
            "fan_percentage_lag1",
            "fan_percentage_roll_mean_30m",
            "current_temperature",
            "temperature",
            "temp_diff",
            "temp_diff_lag1",
            "current_temp_roll_mean_30m",
        ]

        X = df_ml[feature_cols].copy()
        y = pd.to_numeric(df_ml["y_fan_on_future"], errors="coerce").dropna().astype(int)
        X = X.loc[y.index]

        if X.empty or y.empty:
            return {
                "trained": False,
                "room": room,
                "message": "No valid fan feature/target rows after cleaning.",
                "fan_entity_id": fan_entity_id,
                "climate_entity_id": climate_entity_id,
            }

        full_label_counts = y.value_counts().sort_index().to_dict()
        full_classes = sorted(y.unique().tolist())

        if len(full_classes) < 2:
            return {
                "trained": False,
                "room": room,
                "message": (
                    "Not enough target class variety for fan training. "
                    "Need both OFF (0) and ON (1) future fan labels."
                ),
                "fan_entity_id": fan_entity_id,
                "climate_entity_id": climate_entity_id,
                "rows_ml": int(len(df_ml)),
                "label_counts_full": full_label_counts,
                "classes_full": full_classes,
            }

        if len(X) < 5:
            return {
                "trained": False,
                "room": room,
                "message": "Not enough processed rows for a meaningful train/test split.",
                "fan_entity_id": fan_entity_id,
                "climate_entity_id": climate_entity_id,
                "rows_ml": int(len(df_ml)),
                "label_counts_full": full_label_counts,
                "classes_full": full_classes,
            }

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, shuffle=False
        )

        train_label_counts = y_train.value_counts().sort_index().to_dict()
        train_classes = sorted(y_train.unique().tolist())

        if len(train_classes) < 2:
            return {
                "trained": False,
                "room": room,
                "message": (
                    "Fan training split has only one class after time-based split. "
                    "Collect more fan transitions or train later."
                ),
                "fan_entity_id": fan_entity_id,
                "climate_entity_id": climate_entity_id,
                "rows_ml": int(len(df_ml)),
                "rows_train": int(len(X_train)),
                "rows_test": int(len(X_test)),
                "label_counts_full": full_label_counts,
                "classes_full": full_classes,
                "label_counts_train": train_label_counts,
                "classes_train": train_classes,
            }

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

        y_pred = model.predict(X_test)
        report = classification_report(
            y_test,
            y_pred,
            output_dict=True,
            zero_division=0,
        )

        artifact = FanModelArtifact(
            room=room,
            domain="fan",
            cfg=cfg,
            feature_columns=feature_cols,
            model=model,
            metrics=report,
            fan_entity_id=fan_entity_id,
            climate_entity_id=climate_entity_id,
        )

        XGBFanTrainer._save_artifact(room, artifact)

        return {
            "trained": True,
            "room": room,
            "domain": "fan",
            "days": days,
            "fan_entity_id": fan_entity_id,
            "climate_entity_id": climate_entity_id,
            "rows_raw": int(len(df_long)),
            "rows_ml": int(len(df_ml)),
            "rows_train": int(len(X_train)),
            "rows_test": int(len(X_test)),
            "label_counts_full": full_label_counts,
            "classes_full": full_classes,
            "label_counts_train": train_label_counts,
            "classes_train": train_classes,
            "metrics": report,
            "artifact_path": XGBFanTrainer._artifact_path(room),
        }

    @staticmethod
    def _artifact_path(room: str) -> str:
        os.makedirs(ARTIFACT_DIR, exist_ok=True)
        return os.path.join(ARTIFACT_DIR, f"{room}__fan.joblib")

    @staticmethod
    def _save_artifact(room: str, artifact: FanModelArtifact) -> None:
        path = XGBFanTrainer._artifact_path(room)
        joblib.dump(artifact, path)

    @staticmethod
    def load_artifact(room: str) -> Optional[FanModelArtifact]:
        path = XGBFanTrainer._artifact_path(room)
        if not os.path.exists(path):
            return None
        return joblib.load(path)