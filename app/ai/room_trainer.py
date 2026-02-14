from __future__ import annotations

import os
from typing import Any, Dict, Optional

import joblib
import pandas as pd

from app.ai.friend_dataset import FriendInfluxDataset


ARTIFACT_DIR = os.getenv("AI_ARTIFACT_DIR", "app/ai/artifacts/rooms")


class RoomTrainer:

    @staticmethod
    def train_room(*, room: str, days: int = 60) -> Dict[str, Any]:
        df = FriendInfluxDataset.fetch_room_state_df(room=room, days=days)

        if df.empty:
            return {"trained": False, "room": room, "days": days, "message": "No data found."}

        df["hour"] = df["time"].dt.hour
        df["date"] = df["time"].dt.date
        df["weekday_index"] = df["time"].dt.weekday
        df["is_weekend"] = df["weekday_index"] >= 5

        domains = sorted(df["domain"].dropna().unique().tolist())
        domain_profiles: Dict[str, Any] = {}

        for domain in domains:
            sub = df[df["domain"] == domain].copy()
            if sub.empty:
                continue

            profile = RoomTrainer._train_domain(room, domain, days, sub)
            domain_profiles[domain] = profile
            RoomTrainer._save_profile(room, domain, profile)

        return {
            "trained": True,
            "room": room,
            "days": days,
            "domains": domain_profiles,
        }

    @staticmethod
    def _train_domain(room: str, domain: str, days: int, df: pd.DataFrame) -> Dict[str, Any]:

        state_df = df[df["field"] == "state"].copy()
        state_df["value"] = state_df["value"].astype(str).str.lower()

        weekday_df = state_df[state_df["is_weekend"] == False]
        weekend_df = state_df[state_df["is_weekend"] == True]

        profile = {
            "room": room,
            "domain": domain,
            "days": days,
            "weekday": RoomTrainer._compute_probabilities(weekday_df),
            "weekend": RoomTrainer._compute_probabilities(weekend_df),
        }

        # Light brightness handling
        if domain == "light":
            bright_df = df[df["field"] == "brightness"].copy()
            bright_df["brightness"] = pd.to_numeric(bright_df["value"], errors="coerce")
            bright_df = bright_df.dropna(subset=["brightness"])

            profile["weekday"]["avg_brightness"] = RoomTrainer._compute_avg_brightness(
                bright_df[bright_df["is_weekend"] == False]
            )

            profile["weekend"]["avg_brightness"] = RoomTrainer._compute_avg_brightness(
                bright_df[bright_df["is_weekend"] == True]
            )

        return profile

    @staticmethod
    def _compute_probabilities(df: pd.DataFrame) -> Dict[str, Any]:

        if df.empty:
            return {
                "active_days": 0,
                "turn_on_probability": {h: 0.0 for h in range(24)},
            }

        active_days = df["date"].nunique()

        on_df = df[df["value"] == "on"]

        probs: Dict[int, float] = {}
        for h in range(24):
            days_on_this_hour = on_df[on_df["hour"] == h]["date"].nunique()
            probs[h] = round(days_on_this_hour / active_days, 4)

        return {
            "active_days": int(active_days),
            "turn_on_probability": probs,
        }

    @staticmethod
    def _compute_avg_brightness(df: pd.DataFrame) -> Dict[int, float]:
        result: Dict[int, float] = {}
        for h in range(24):
            vals = df[df["hour"] == h]["brightness"]
            if not vals.empty:
                result[h] = float(round(vals.mean(), 2))
        return result

    @staticmethod
    def _save_profile(room: str, domain: str, profile: Dict[str, Any]) -> None:
        os.makedirs(ARTIFACT_DIR, exist_ok=True)
        path = os.path.join(ARTIFACT_DIR, f"{room}__{domain}.joblib")
        joblib.dump(profile, path)

    @staticmethod
    def load_profile(room: str, domain: str) -> Optional[Dict[str, Any]]:
        path = os.path.join(ARTIFACT_DIR, f"{room}__{domain}.joblib")
        if not os.path.exists(path):
            return None
        return joblib.load(path)
