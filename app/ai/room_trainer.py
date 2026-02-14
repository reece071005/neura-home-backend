import pandas as pd
from collections import defaultdict, Counter
from typing import Dict, Any, Optional

from app.ai.friend_dataset import FriendInfluxDataset


class RoomTrainer:
    """
    Trains a room profile from friend's InfluxDB (Home Assistant integration schema).

    It splits behavior by domain (light / climate / cover / fan ...)

    Output example:

    {
      "trained": true,
      "room": "guest_room",
      "domains": {
        "light": {
          "on_probability": {...},
          "avg_brightness": {...}
        },
        "climate": {
          "on_probability": {...},
          "avg_temperature": {...},
          "mode_hvac": {...}
        }
      }
    }
    """

    @staticmethod
    def _mode(values: list[str]) -> Optional[str]:
        if not values:
            return None
        c = Counter(values)
        return c.most_common(1)[0][0]

    @staticmethod
    def train_room(room: str, days: int = 60) -> Dict[str, Any]:
        df = FriendInfluxDataset.fetch_room_state_df(room=room, days=days)

        if df.empty:
            return {"trained": False, "message": "No data found."}

        df["hour"] = pd.to_datetime(df["time"]).dt.hour

        domains_result: Dict[str, Any] = {}

        # Get all domains for this room
        domains = sorted(df["domain"].dropna().unique().tolist())

        for domain in domains:
            domain_df = df[df["domain"] == domain].copy()
            if domain_df.empty:
                continue

            domain_profile: Dict[str, Any] = {}

            # --------------------------
            # ON probability per hour
            # --------------------------
            state_df = domain_df[domain_df["_field"] == "state"].copy()

            if not state_df.empty:
                state_df["time"] = pd.to_datetime(state_df["time"])
                state_df = state_df.sort_values("time")

                state_df["_value"] = state_df["_value"].astype(str).str.lower()

                # Detect transitions
                state_df["prev_state"] = state_df["_value"].shift(1)
                state_df["turn_on_event"] = (
                        (state_df["_value"] == "on") &
                        (state_df["prev_state"] != "on")
                )

                state_df["hour"] = state_df["time"].dt.hour
                state_df["date"] = state_df["time"].dt.date

                # Count unique days with turn-on per hour
                turn_on_events = state_df[state_df["turn_on_event"]]

                grouped = (
                    turn_on_events.groupby(["date", "hour"])
                    .size()
                    .reset_index(name="count")
                )

                total_days = state_df["date"].nunique()

                on_probability = {}
                for hour in range(24):
                    days_with_event = grouped[grouped["hour"] == hour]["date"].nunique()
                    prob = days_with_event / total_days if total_days > 0 else 0
                    on_probability[str(hour)] = round(prob, 4)

                domain_profile["turn_on_probability"] = on_probability

            # --------------------------
            # LIGHT extras
            # --------------------------
            if domain == "light":
                bright_df = domain_df[domain_df["_field"] == "brightness"]

                avg_brightness = {}
                for hour in range(24):
                    sub = bright_df[bright_df["hour"] == hour]
                    if sub.empty:
                        avg_brightness[str(hour)] = None
                    else:
                        # HA brightness usually 0-255
                        try:
                            avg_brightness[str(hour)] = round(float(sub["_value"].astype(float).mean()), 2)
                        except Exception:
                            avg_brightness[str(hour)] = None

                domain_profile["avg_brightness"] = avg_brightness

            # --------------------------
            # CLIMATE extras
            # --------------------------
            if domain == "climate":
                # Temperature can be in different fields
                temp_df = domain_df[domain_df["_field"].isin(["temperature", "current_temperature"])]
                hvac_df = domain_df[domain_df["_field"] == "hvac_mode_str"]

                avg_temperature = {}
                for hour in range(24):
                    sub = temp_df[temp_df["hour"] == hour]
                    if sub.empty:
                        avg_temperature[str(hour)] = None
                    else:
                        try:
                            avg_temperature[str(hour)] = round(float(sub["_value"].astype(float).mean()), 2)
                        except Exception:
                            avg_temperature[str(hour)] = None

                mode_hvac = {}
                for hour in range(24):
                    sub = hvac_df[hvac_df["hour"] == hour]
                    if sub.empty:
                        mode_hvac[str(hour)] = None
                    else:
                        vals = [str(v).lower() for v in sub["_value"].tolist() if v is not None]
                        mode_hvac[str(hour)] = RoomTrainer._mode(vals)

                domain_profile["avg_temperature"] = avg_temperature
                domain_profile["mode_hvac"] = mode_hvac

            domains_result[domain] = domain_profile

        return {
            "trained": True,
            "room": room,
            "days": days,
            "domains": domains_result,
        }
