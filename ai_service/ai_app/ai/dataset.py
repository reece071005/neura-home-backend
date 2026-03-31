from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional
import os
import pandas as pd
from ai_app.core.influxdb_init import get_influx_query_api


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)

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
        start = _utc_now() - timedelta(hours=window.hours)

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
        start = _utc_now() - timedelta(hours=window.hours)

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
