from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Optional

import pandas as pd

from ai_app.core.demo_time import get_simulated_utc_now
from ai_app.core.influxdb_init import get_influx_query_api


@dataclass
class FriendWindow:
    days: int = 60
class FriendInfluxDataset:


       # guys this is for reading from the local project influxdb, not the remote one.
        #it will map and use the local measurement schema
    @staticmethod
    def fetch_room_state_df(*, room: str, days: int = 60) -> pd.DataFrame:
        start = _sync_now_minus_days(days)

        flux = f"""
    from(bucket: "{_get_bucket()}")
        |> range(start: {start.isoformat()})
        |> filter(fn: (r) => r._measurement == "device_state")
        |> keep(columns: ["_time","domain","entity_id","_field","_value"])
        """.strip()

        query_api = get_influx_query_api()
        tables = query_api.query_data_frame(flux)

        if tables is None:
            return pd.DataFrame()

        df = tables if not isinstance(tables, list) else pd.concat(tables, ignore_index=True)

        if df.empty:
            return df

        df = df.rename(columns={"_time": "time", "_value": "value", "_field": "field"})
        df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
        df = df.dropna(subset=["time"])

        room_normalized = room.strip().lower().replace(" ", "_")

        df = df[df["entity_id"].str.lower().str.contains(room_normalized)]

        keep = ["time", "domain", "entity_id", "field", "value"]
        for col in keep:
            if col not in df.columns:
                df[col] = None

        return df[keep].copy()

    @staticmethod
    def fetch_latest_state(
        *,
        entity_id: str,
        domain: str = "binary_sensor",
        field: str = "state",
        lookback_minutes: int = 60 * 24,
    ) -> Optional[str]:
        start = _sync_now_minus_minutes(lookback_minutes)

        flux = f"""
from(bucket: "{_get_bucket()}")
  |> range(start: {start.isoformat()})
  |> filter(fn: (r) => r._measurement == "device_state")
  |> filter(fn: (r) => r.domain == "{domain}")
  |> filter(fn: (r) => r.entity_id == "{entity_id}")
  |> filter(fn: (r) => r._field == "{field}")
  |> keep(columns: ["_time","_value"])
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: 1)
        """.strip()

        query_api = get_influx_query_api()
        tables = query_api.query_data_frame(flux)

        if tables is None:
            return None

        df = tables if not isinstance(tables, list) else pd.concat(tables, ignore_index=True)
        if df.empty or "_value" not in df.columns:
            return None

        v = df["_value"].iloc[0]
        if v is None:
            return None

        return str(v).strip().lower()

    @staticmethod
    def fetch_latest_numeric(
        *,
        entity_id: str,
        domain: str,
        field: str,
        lookback_minutes: int = 60 * 24,
    ) -> Optional[float]:
        start = _sync_now_minus_minutes(lookback_minutes)

        flux = f"""
from(bucket: "{_get_bucket()}")
  |> range(start: {start.isoformat()})
  |> filter(fn: (r) => r._measurement == "device_state")
  |> filter(fn: (r) => r.domain == "{domain}")
  |> filter(fn: (r) => r.entity_id == "{entity_id}")
  |> filter(fn: (r) => r._field == "{field}")
  |> keep(columns: ["_time","_value"])
  |> sort(columns: ["_time"], desc: true)
  |> limit(n: 1)
        """.strip()

        query_api = get_influx_query_api()
        tables = query_api.query_data_frame(flux)

        if tables is None:
            return None

        df = tables if not isinstance(tables, list) else pd.concat(tables, ignore_index=True)
        if df.empty or "_value" not in df.columns:
            return None

        try:
            return float(df["_value"].iloc[0])
        except Exception:
            return None

    @staticmethod
    def fetch_motion_recent(
        *,
        entity_id: str,
        minutes: int = 5,
    ) -> bool:
        start = _sync_now_minus_minutes(minutes)

        flux = f"""
from(bucket: "{_get_bucket()}")
  |> range(start: {start.isoformat()})
  |> filter(fn: (r) => r._measurement == "device_state")
  |> filter(fn: (r) => r.domain == "binary_sensor")
  |> filter(fn: (r) => r.entity_id == "{entity_id}")
  |> filter(fn: (r) => r._field == "state")
  |> filter(fn: (r) => r._value == "on")
  |> limit(n: 1)
        """.strip()

        query_api = get_influx_query_api()
        tables = query_api.query_data_frame(flux)

        if tables is None:
            return False

        df = tables if not isinstance(tables, list) else pd.concat(tables, ignore_index=True)
        return not df.empty


def _get_bucket() -> str:
    import os
    return os.getenv("INFLUX_BUCKET", "smart_home")


def _sync_now_minus_days(days: int):
    import asyncio
    from datetime import datetime, timezone

    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            return datetime.now(timezone.utc) - timedelta(days=days)
    except RuntimeError:
        pass

    now = asyncio.run(get_simulated_utc_now())
    return now - timedelta(days=days)


def _sync_now_minus_minutes(minutes: int):
    import asyncio
    from datetime import datetime, timezone

    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            return datetime.now(timezone.utc) - timedelta(minutes=minutes)
    except RuntimeError:
        pass

    now = asyncio.run(get_simulated_utc_now())
    return now - timedelta(minutes=minutes)