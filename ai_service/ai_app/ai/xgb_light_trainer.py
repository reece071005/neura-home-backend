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

        # fetch long format from friend influx
        df_long = FriendInfluxDataset.fetch_room_state_df(room=room, days=days)
        if df_long.empty:
            return {
                "trained": False,
                "room": room,
                "message": "No data returned from friend influx.",
            }

        # fiilter domain=light
        df_long = df_long[df_long["domain"] == "light"].copy()
        if df_long.empty:
            return {
                "trained": False,
                "room": room,
                "message": "No light data found for this room.",
            }

        # 3) Pivot to wide
        df_wide = TimeSeriesBuilder.pivot_events_to_wide(df_long)
        if df_wide.empty:
            return {
                "trained": False,
                "room": room,
                "message": "Pivot failed (empty wide dataframe).",
            }

        # resample to 5 min time grid, helps a lot
        df_ts = TimeSeriesBuilder.resample_room_domain(df_wide, cfg=cfg)
        if df_ts.empty:
            return {
                "trained": False,
                "room": room,
                "message": "Resampling produced no usable rows.",
            }

        # 5) build ml dataset
        df_ml = TimeSeriesBuilder.build_light_classification_dataset(df_ts, cfg=cfg)

        if df_ml.empty or len(df_ml) < cfg.min_rows:
            return {
                "trained": False,
                "room": room,
                "message": (
                    f"Not enough training rows after processing. "
                    f"Rows={len(df_ml)} min_required={cfg.min_rows}"
                ),
                "rows_raw": int(len(df_long)),
                "rows_ts": int(len(df_ts)),
                "rows_ml": int(len(df_ml)),
            }

        # 6) Features / target
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

        X = df_ml[feature_cols].copy()
        y = df_ml["y_on_future"].copy()

        y = pd.to_numeric(y, errors="coerce").dropna().astype(int)

        #alligning x  with cleaned y index
        X = X.loc[y.index]

        if X.empty or y.empty:
            return {
                "trained": False,
                "room": room,
                "message": "No valid feature/target rows after cleaning.",
                "rows_raw": int(len(df_long)),
                "rows_ts": int(len(df_ts)),
                "rows_ml": int(len(df_ml)),
            }

        #  full dataset must contain at least 2 classes
        full_label_counts = y.value_counts().sort_index().to_dict()
        full_classes = sorted(y.unique().tolist())

        if len(full_classes) < 2:
            return {
                "trained": False,
                "room": room,
                "message": (
                    "Not enough target class variety for training. "
                    "Need both OFF (0) and ON (1) future labels."
                ),
                "rows_raw": int(len(df_long)),
                "rows_ts": int(len(df_ts)),
                "rows_ml": int(len(df_ml)),
                "label_counts_full": full_label_counts,
                "classes_full": full_classes,
            }

        #   need enough rows for a meaningful split
        if len(X) < 5:
            return {
                "trained": False,
                "room": room,
                "message": (
                    "Not enough processed rows for a train/test split. "
                    "Collect more light on/off history first."
                ),
                "rows_raw": int(len(df_long)),
                "rows_ts": int(len(df_ts)),
                "rows_ml": int(len(df_ml)),
                "label_counts_full": full_label_counts,
                "classes_full": full_classes,
            }


        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, shuffle=False
        )

        if len(X_train) == 0 or len(X_test) == 0:
            return {
                "trained": False,
                "room": room,
                "message": "Train/test split produced an empty train or test set.",
                "rows_raw": int(len(df_long)),
                "rows_ts": int(len(df_ts)),
                "rows_ml": int(len(df_ml)),
                "rows_train": int(len(X_train)),
                "rows_test": int(len(X_test)),
                "label_counts_full": full_label_counts,
                "classes_full": full_classes,
            }

        # train split must also contain at least 2 classes
        train_label_counts = y_train.value_counts().sort_index().to_dict()
        train_classes = sorted(y_train.unique().tolist())

        if len(train_classes) < 2:
            return {
                "trained": False,
                "room": room,
                "message": (
                    "Training split has only one class after time-based split. "
                    "Collect more light transitions or train later when more varied history exists."
                ),
                "rows_raw": int(len(df_long)),
                "rows_ts": int(len(df_ts)),
                "rows_ml": int(len(df_ml)),
                "rows_train": int(len(X_train)),
                "rows_test": int(len(X_test)),
                "label_counts_full": full_label_counts,
                "classes_full": full_classes,
                "label_counts_train": train_label_counts,
                "classes_train": train_classes,
            }

        # 8) train model
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

        # evaluating model
        y_pred = model.predict(X_test)

        # safer report in small datasets
        report = classification_report(
            y_test,
            y_pred,
            output_dict=True,
            zero_division=0,
        )

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
            "rows_train": int(len(X_train)),
            "rows_test": int(len(X_test)),
            "label_counts_full": full_label_counts,
            "classes_full": full_classes,
            "label_counts_train": train_label_counts,
            "classes_train": train_classes,
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