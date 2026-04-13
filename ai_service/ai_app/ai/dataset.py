from __future__ import annotations
from dataclasses import dataclass
from datetime import timedelta
from datetime import datetime
from typing import Optional
import os
import pandas as pd
from ai_app.core.influxdb_init import get_influx_query_api
from ai_app.core.demo_time import get_simulated_utc_now


@dataclass
class DatasetWindow:
    hours: int = 168


class InfluxDataset:
    @staticmethod
    def fetch_device_state_df(
        *,
        entity_id: Optional[str] = None,
        domain: Optional[str] = None,
        window: DatasetWindow = DatasetWindow(),
    ) -> pd.DataFrame:
        bucket = os.getenv("INFLUX_BUCKET", "smart_home")
        start = _sync_now_minus_hours(window.hours)

        filters = [f'r._measurement == "device_state"']
        if entity_id:
            filters.append(f'r.entity_id == "{entity_id}"')
        if domain:
            filters.append(f'r.domain == "{domain}"')

        filter_expr = " and ".join(filters)

        flux = f"""
from(bucket: "{bucket}")
  |> range(start: {start.isoformat()})
  |> filter(fn: (r) => {filter_expr})
  |> keep(columns: ["_time","_field","_value","entity_id","domain","area","source"])
        """.strip()

        query_api = get_influx_query_api()
        tables = query_api.query_data_frame(flux)

        if tables is None or (isinstance(tables, list) and len(tables) == 0):
            return pd.DataFrame()

        df = tables if not isinstance(tables, list) else pd.concat(tables, ignore_index=True)
        if df.empty:
            return df

        wide = df.pivot_table(
            index=["_time", "entity_id", "domain", "area", "source"],
            columns="_field",
            values="_value",
            aggfunc="last"
        ).reset_index()

        wide.columns = [str(c) for c in wide.columns]
        wide = wide.rename(columns={"_time": "time"})
        return wide

    @staticmethod
    def fetch_user_actions_df(*, user_id: int, window: DatasetWindow = DatasetWindow()) -> pd.DataFrame:
        bucket = os.getenv("INFLUX_BUCKET", "smart_home")
        start = _sync_now_minus_hours(window.hours)

        flux = f"""
from(bucket: "{bucket}")
  |> range(start: {start.isoformat()})
  |> filter(fn: (r) => r._measurement == "user_action")
  |> filter(fn: (r) => r.user_id == "{user_id}")
  |> keep(columns: ["_time","_field","_value","user_id","entity_id","domain","action","meta_json"])
        """.strip()

        query_api = get_influx_query_api()
        tables = query_api.query_data_frame(flux)

        if tables is None or (isinstance(tables, list) and len(tables) == 0):
            return pd.DataFrame()

        df = tables if not isinstance(tables, list) else pd.concat(tables, ignore_index=True)
        if df.empty:
            return df

        df = df.rename(columns={"_time": "time", "_value": "value"})
        return df

    @staticmethod
    def fetch_room_device_state_df(
            *,
            entity_ids: list[str],
            window: DatasetWindow = DatasetWindow(),
    ) -> pd.DataFrame:
        bucket = os.getenv("INFLUX_BUCKET", "smart_home")
        start = _sync_now_minus_hours(window.hours)

        if not entity_ids:
            return pd.DataFrame()

        entity_filters = " or ".join([f'r.entity_id == "{eid}"' for eid in entity_ids])

        flux = f"""
from(bucket: "{bucket}")
    |> range(start: {start.isoformat()})
    |> filter(fn: (r) => r._measurement == "device_state")
    |> filter(fn: (r) => {entity_filters})
    |> keep(columns: ["_time","_field","_value","entity_id","domain","area","source"])
        """.strip()

        query_api = get_influx_query_api()
        tables = query_api.query_data_frame(flux)

        if tables is None or (isinstance(tables, list) and len(tables) == 0):
            return pd.DataFrame()

        df = tables if not isinstance(tables, list) else pd.concat(tables, ignore_index=True)
        if df.empty:
            return df

        for col in ["entity_id", "domain", "area", "source"]:
            if col not in df.columns:
                df[col] = None

        wide = df.pivot_table(
            index=["_time", "entity_id", "domain", "source"],
            columns="_field",
            values="_value",
            aggfunc="last"
        ).reset_index()

        wide.columns = [str(c) for c in wide.columns]
        wide = wide.rename(columns={"_time": "time"})
        wide["time"] = pd.to_datetime(wide["time"], utc=True, errors="coerce")
        wide = wide.dropna(subset=["time"])
        return wide


def _sync_now_minus_hours(hours: int):
    import asyncio

    try:
        loop = asyncio.get_running_loop()
        if loop.is_running():
            # fallback to real utc if called in a strict sync context inside acitve loop
            from datetime import datetime, timezone
            return datetime.now(timezone.utc) - timedelta(hours=hours)
    except RuntimeError:
        pass

    now = asyncio.run(get_simulated_utc_now())
    return now - timedelta(hours=hours)