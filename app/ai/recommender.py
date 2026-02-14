from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional
import os
import joblib
import pandas as pd

from app.ai.dataset import InfluxDataset, DatasetWindow


MODEL_PATH = os.getenv("AI_MODEL_PATH", "app/ai/artifacts/behavior_profile.joblib")


@dataclass
class BehaviorProfile:
    top_entities: List[str]
    peak_hours: Dict[str, int]


class Recommender:
    @staticmethod
    def train_behavior_profile(*, window_hours: int = 24 * 14) -> Dict[str, Any]:
        df = InfluxDataset.fetch_device_state_df(window=DatasetWindow(hours=window_hours))

        if df.empty or "entity_id" not in df.columns or "time" not in df.columns:
            profile = BehaviorProfile(top_entities=[], peak_hours={})
            Recommender._save_profile(profile)
            return {"trained": True, "message": "No data found; saved empty profile.", "profile": profile.__dict__}

        counts = df["entity_id"].value_counts().head(10)
        top_entities = counts.index.tolist()

        df2 = df.copy()
        df2["hour"] = pd.to_datetime(df2["time"]).dt.hour

        peak_hours: Dict[str, int] = {}
        for ent in top_entities:
            sub = df2[df2["entity_id"] == ent]
            if sub.empty:
                continue
            peak_hour = int(sub["hour"].value_counts().idxmax())
            peak_hours[ent] = peak_hour

        profile = BehaviorProfile(top_entities=top_entities, peak_hours=peak_hours)
        Recommender._save_profile(profile)

        return {"trained": True, "message": "Behavior profile trained.", "profile": profile.__dict__}

    @staticmethod
    def recommend_for_user(*, user_id: Optional[int] = None) -> Dict[str, Any]:
        profile = Recommender._load_profile()
        recs: List[str] = []

        if not profile.top_entities:
            return {
                "user_id": user_id,
                "recommendations": ["Not enough history yet. Run /influx/snapshot a few times across days to build patterns."],
                "weekly_plan": [],
            }

        for ent in profile.top_entities[:5]:
            hour = profile.peak_hours.get(ent)
            if hour is None:
                continue
            recs.append(
                f"You most often use **{ent}** around **{hour:02d}:00**. Consider creating an automation for it."
            )

        if user_id is not None:
            actions_df = InfluxDataset.fetch_user_actions_df(user_id=user_id, window=DatasetWindow(hours=24 * 7))
            if not actions_df.empty:
                top_actions = (
                    actions_df.groupby(["entity_id", "action"])
                    .size()
                    .sort_values(ascending=False)
                    .head(5)
                )
                for (entity_id, action), n in top_actions.items():
                    recs.append(
                        f"You performed **{action}** on **{entity_id}** **{int(n)}** times this week — consider a shortcut/scene."
                    )

        weekly_plan = Recommender._weekly_plan_from_profile(profile)
        return {"user_id": user_id, "recommendations": recs, "weekly_plan": weekly_plan}

    @staticmethod
    def _weekly_plan_from_profile(profile: BehaviorProfile) -> List[Dict[str, Any]]:
        plan: List[Dict[str, Any]] = []
        for ent in profile.top_entities[:5]:
            hour = profile.peak_hours.get(ent, 19)
            plan.append(
                {"entity_id": ent, "suggested_time": f"{hour:02d}:00", "note": "Based on your most common usage hour."}
            )
        return plan

    @staticmethod
    def _save_profile(profile: BehaviorProfile) -> None:
        os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)
        joblib.dump(profile, MODEL_PATH)

    @staticmethod
    def _load_profile() -> BehaviorProfile:
        if not os.path.exists(MODEL_PATH):
            return BehaviorProfile(top_entities=[], peak_hours={})
        try:
            return joblib.load(MODEL_PATH)
        except Exception:
            return BehaviorProfile(top_entities=[], peak_hours={})
