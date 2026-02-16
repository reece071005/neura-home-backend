from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

import pandas as pd


@dataclass(frozen=True)
class BuildConfig:
    freq: str = "5min"          # resample frequency
    horizon_minutes: int = 15   # predict next 15 minutes
    min_rows: int = 500         # minimum rows to train


def _encode_on_off(v: object) -> Optional[int]:
    if v is None:
        return None
    s = str(v).strip().lower()
    if s == "on":
        return 1
    if s == "off":
        return 0
    return None


class TimeSeriesBuilder:
    """
    Converts Influx event-based records into a fixed-interval time series dataset.
    """

    @staticmethod
    def pivot_events_to_wide(df_long: pd.DataFrame) -> pd.DataFrame:
        """
        Input (long):
            time, domain, entity_id, field, value
        Output (wide):
            time, domain, entity_id, state, brightness, ...
        """
        if df_long.empty:
            return pd.DataFrame()

        df = df_long.copy()

        # normalize column names
        if "field" not in df.columns:
            df = df.rename(columns={"_field": "field"})
        if "value" not in df.columns:
            df = df.rename(columns={"_value": "value"})

        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.dropna(subset=["time", "field"])

        wide = (
            df.pivot_table(
                index=["time", "domain", "entity_id"],
                columns="field",
                values="value",
                aggfunc="last",
            )
            .reset_index()
        )

        wide.columns = [str(c) for c in wide.columns]
        wide = wide.sort_values("time").reset_index(drop=True)
        return wide

    @staticmethod
    def resample_room_domain(
        df_wide: pd.DataFrame,
        *,
        cfg: BuildConfig = BuildConfig(),
    ) -> pd.DataFrame:
        """
        Resample to a fixed time grid.
        - Forward-fill state + brightness.
        """
        if df_wide.empty:
            return pd.DataFrame()

        df = df_wide.copy()
        df["time"] = pd.to_datetime(df["time"], utc=True)

        # Expect only one room/domain in this df.
        domain = str(df["domain"].iloc[0])
        entity_id = str(df["entity_id"].iloc[0])

        df = df.set_index("time").sort_index()

        # Keep only fields we care about for light.
        keep_cols = []
        for c in ["state", "brightness"]:
            if c in df.columns:
                keep_cols.append(c)

        df = df[keep_cols]

        # Resample to fixed frequency.
        df = df.resample(cfg.freq).last()

        # Forward fill state + brightness
        if "state" in df.columns:
            df["state"] = df["state"].ffill()
        if "brightness" in df.columns:
            df["brightness"] = pd.to_numeric(df["brightness"], errors="coerce")
            df["brightness"] = df["brightness"].ffill()

        df = df.reset_index()
        df["domain"] = domain
        df["entity_id"] = entity_id

        return df

    @staticmethod
    def build_light_classification_dataset(
        df_ts: pd.DataFrame,
        *,
        cfg: BuildConfig = BuildConfig(),
    ) -> pd.DataFrame:
        """
        Builds:
          X features at time t
          y = whether light is ON at time t + horizon
        """
        if df_ts.empty:
            return pd.DataFrame()

        df = df_ts.copy()
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.sort_values("time").reset_index(drop=True)

        # encode state
        df["state_on"] = df["state"].apply(_encode_on_off)

        # brightness
        if "brightness" not in df.columns:
            df["brightness"] = None
        df["brightness"] = pd.to_numeric(df["brightness"], errors="coerce").fillna(0.0)

        # Time features
        df["hour"] = df["time"].dt.hour
        df["weekday"] = df["time"].dt.weekday
        df["is_weekend"] = (df["weekday"] >= 5).astype(int)

        # Lag features (previous timestep)
        df["state_on_lag1"] = df["state_on"].shift(1)
        df["brightness_lag1"] = df["brightness"].shift(1)

        # Rolling brightness mean (30 minutes = 6 steps at 5min)
        df["brightness_roll_mean_30m"] = df["brightness"].rolling(window=6, min_periods=1).mean()

        # Target: ON in horizon
        step_minutes = int(pd.Timedelta(cfg.freq).total_seconds() // 60)
        horizon_steps = max(1, cfg.horizon_minutes // step_minutes)

        df["y_on_future"] = df["state_on"].shift(-horizon_steps)

        # Clean rows
        df = df.dropna(subset=["state_on", "state_on_lag1", "y_on_future"])
        df["y_on_future"] = df["y_on_future"].astype(int)

        # Keep final columns
        out = df[
            [
                "time",
                "entity_id",
                "domain",
                "hour",
                "weekday",
                "is_weekend",
                "state_on",
                "state_on_lag1",
                "brightness",
                "brightness_lag1",
                "brightness_roll_mean_30m",
                "y_on_future",
            ]
        ].copy()

        return out
