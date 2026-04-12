from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

import pandas as pd


@dataclass(frozen=True)
class BuildConfig:
    freq: str = "5min"          # resample frequency
    horizon_minutes: int = 15   # predict next 15 minutes
    min_rows: int = 30         # minimum rows to train


def _encode_on_off(v: object) -> Optional[int]:
    if v is None:
        return None
    s = str(v).strip().lower()
    if s == "on":
        return 1
    if s == "off":
        return 0
    return None

def _encode_hvac_action(v: object) -> Optional[int]:
    """
    Binary encoding:
      1 = heating/cooling (active)
      0 = idle/fan/off/unknown
    """
    if v is None:
        return None
    s = str(v).strip().lower()
    if s in {"heating", "cooling"}:
        return 1
    if s in {"idle", "fan", "off", "unknown", "none", ""}:
        return 0
    # treat anything else as inactive for now
    return 0


class TimeSeriesBuilder:
    """
    Converts Influx event-based records into a fixed-interval time series dataset.
    """

    @staticmethod
    def build_climate_classification_dataset(
        df_ts: pd.DataFrame,
        *,
        cfg: BuildConfig = BuildConfig(),
    ) -> pd.DataFrame:
        """
        Predict whether climate will be ACTIVE in the future.
        ACTIVE means hvac_action_str in {heating, cooling}
        """
        if df_ts.empty:
            return pd.DataFrame()

        df = df_ts.copy()
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.sort_values("time").reset_index(drop=True)

        # Required columns
        if "hvac_action_str" not in df.columns:
            return pd.DataFrame()

        df["hvac_active"] = df["hvac_action_str"].apply(_encode_hvac_action)

        # Temperatures
        for col in ["current_temperature", "temperature"]:
            if col not in df.columns:
                df[col] = None
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df["current_temperature"] = df["current_temperature"].ffill()
        df["temperature"] = df["temperature"].ffill()

        # If still NaN, fill with 0 (not ideal but prevents crashes)
        df["current_temperature"] = df["current_temperature"].fillna(0.0)
        df["temperature"] = df["temperature"].fillna(0.0)

        df["temp_diff"] = df["temperature"] - df["current_temperature"]

        # Time features
        df["hour"] = df["time"].dt.hour
        df["weekday"] = df["time"].dt.weekday
        df["is_weekend"] = (df["weekday"] >= 5).astype(int)

        # Lag features
        df["hvac_active_lag1"] = df["hvac_active"].shift(1)
        df["temp_diff_lag1"] = df["temp_diff"].shift(1)

        # Rolling mean of current temperature (30 min)
        df["current_temp_roll_mean_30m"] = df["current_temperature"].rolling(window=6, min_periods=1).mean()

        # Target
        step_minutes = int(pd.Timedelta(cfg.freq).total_seconds() // 60)
        horizon_steps = max(1, cfg.horizon_minutes // step_minutes)

        df["y_hvac_active_future"] = df["hvac_active"].shift(-horizon_steps)

        df = df.dropna(subset=["hvac_active", "hvac_active_lag1", "y_hvac_active_future"])
        df["y_hvac_active_future"] = df["y_hvac_active_future"].astype(int)

        out = df[
            [
                "time",
                "entity_id",
                "domain",
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
                "y_hvac_active_future",
            ]
        ].copy()

        return out


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
        if df_wide.empty:
            return pd.DataFrame()

        df = df_wide.copy()
        df["time"] = pd.to_datetime(df["time"], utc=True)

        domain = str(df["domain"].iloc[0])
        entity_id = str(df["entity_id"].iloc[0])

        df = df.set_index("time").sort_index()

        # Resample
        df = df.resample(cfg.freq).last()

        # Forward fill ALL useful columns
        for col in df.columns:
            df[col] = df[col].ffill()

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

    @staticmethod
    def build_climate_temperature_regression_dataset(
        df_ts: pd.DataFrame,
        *,
        cfg: BuildConfig = BuildConfig(),
    ) -> pd.DataFrame:
        """
        Predict the future climate setpoint temperature.
        y = temperature at t + horizon
        """
        if df_ts.empty:
            return pd.DataFrame()

        df = df_ts.copy()
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df = df.sort_values("time").reset_index(drop=True)

        # Ensure numeric
        for col in ["current_temperature", "temperature"]:
            if col not in df.columns:
                df[col] = None
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df["current_temperature"] = df["current_temperature"].ffill()
        df["temperature"] = df["temperature"].ffill()

        # Drop if still missing
        df = df.dropna(subset=["current_temperature", "temperature"])
        if df.empty:
            return pd.DataFrame()

        df["temp_diff"] = df["temperature"] - df["current_temperature"]

        # Time features
        df["hour"] = df["time"].dt.hour
        df["weekday"] = df["time"].dt.weekday
        df["is_weekend"] = (df["weekday"] >= 5).astype(int)

        # Lag features
        df["setpoint_lag1"] = df["temperature"].shift(1)
        df["current_temp_lag1"] = df["current_temperature"].shift(1)
        df["temp_diff_lag1"] = df["temp_diff"].shift(1)

        # Rolling mean temperature (30 min)
        df["current_temp_roll_mean_30m"] = df["current_temperature"].rolling(window=6, min_periods=1).mean()

        # Target
        step_minutes = int(pd.Timedelta(cfg.freq).total_seconds() // 60)
        horizon_steps = max(1, cfg.horizon_minutes // step_minutes)

        df["y_setpoint_future"] = df["temperature"].shift(-horizon_steps)

        df = df.dropna(subset=["setpoint_lag1", "y_setpoint_future"])

        out = df[
            [
                "time",
                "entity_id",
                "domain",
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
                "y_setpoint_future",
            ]
        ].copy()

        return out


    @staticmethod
    def build_fan_classification_dataset(
        fan_ts: pd.DataFrame,
        climate_ts: pd.DataFrame | None = None,
        *,
        cfg: BuildConfig = BuildConfig(),
    ) -> pd.DataFrame:
        if fan_ts.empty:
            return pd.DataFrame()

        fan_df = fan_ts.copy()
        fan_df["time"] = pd.to_datetime(fan_df["time"], utc=True)
        fan_df = fan_df.sort_values("time").reset_index(drop=True)

        if "state" not in fan_df.columns:
            fan_df["state"] = None
        fan_df["fan_state_on"] = fan_df["state"].apply(_encode_on_off)

        if "percentage" not in fan_df.columns:
            fan_df["percentage"] = None
        fan_df["fan_percentage"] = pd.to_numeric(fan_df["percentage"], errors="coerce").fillna(0.0)

        # Merge climate context if available
        if climate_ts is not None and not climate_ts.empty:
            climate_df = climate_ts.copy()
            climate_df["time"] = pd.to_datetime(climate_df["time"], utc=True)
            climate_df = climate_df.sort_values("time").reset_index(drop=True)

            keep_cols = ["time", "current_temperature", "temperature"]
            for col in keep_cols:
                if col not in climate_df.columns:
                    climate_df[col] = None

            climate_df["current_temperature"] = pd.to_numeric(
                climate_df["current_temperature"], errors="coerce"
            )
            climate_df["temperature"] = pd.to_numeric(
                climate_df["temperature"], errors="coerce"
            )

            df = pd.merge_asof(
                fan_df.sort_values("time"),
                climate_df[keep_cols].sort_values("time"),
                on="time",
                direction="backward",
            )
        else:
            df = fan_df.copy()
            df["current_temperature"] = None
            df["temperature"] = None

        df["current_temperature"] = pd.to_numeric(df["current_temperature"], errors="coerce").ffill()
        df["temperature"] = pd.to_numeric(df["temperature"], errors="coerce").ffill()

        df["current_temperature"] = df["current_temperature"].fillna(0.0)
        df["temperature"] = df["temperature"].fillna(0.0)

        df["temp_diff"] = df["temperature"] - df["current_temperature"]

        df["hour"] = df["time"].dt.hour
        df["weekday"] = df["time"].dt.weekday
        df["is_weekend"] = (df["weekday"] >= 5).astype(int)

        df["fan_state_on_lag1"] = df["fan_state_on"].shift(1)
        df["fan_percentage_lag1"] = df["fan_percentage"].shift(1)
        df["fan_percentage_roll_mean_30m"] = df["fan_percentage"].rolling(window=6, min_periods=1).mean()

        df["temp_diff_lag1"] = df["temp_diff"].shift(1)
        df["current_temp_roll_mean_30m"] = df["current_temperature"].rolling(window=6, min_periods=1).mean()

        step_minutes = int(pd.Timedelta(cfg.freq).total_seconds() // 60)
        horizon_steps = max(1, cfg.horizon_minutes // step_minutes)

        df["y_fan_on_future"] = df["fan_state_on"].shift(-horizon_steps)

        df = df.dropna(subset=["fan_state_on", "fan_state_on_lag1", "y_fan_on_future"])
        df["y_fan_on_future"] = df["y_fan_on_future"].astype(int)

        out = df[
            [
                "time",
                "entity_id",
                "domain",
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
                "y_fan_on_future",
            ]
        ].copy()

        return out







