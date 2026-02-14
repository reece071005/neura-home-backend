from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import os
import pandas as pd
from influxdb_client import InfluxDBClient


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class FriendWindow:
    days: int = 60


class FriendInfluxDataset:
    """
    Reads room-level state data from FRIEND's InfluxDB instance.
    This is NOT your local Influx.

    Data format (from your screenshots):
    - _measurement == "state"
    - domain: "light", "climate", ...
    - entity_id: "guest_room", "kitchen", ...
    - _field: "state", "brightness", ...
    - _value: mixed type (string, int, float)
    """

    @staticmethod
    def _get_client() -> InfluxDBClient:
        url = os.getenv("FRIEND_INFLUX_URL")
        token = os.getenv("FRIEND_INFLUX_TOKEN")
        org = os.getenv("FRIEND_INFLUX_ORG")

        if not url or not token or not org:
            raise RuntimeError(
                "Missing FRIEND_INFLUX_URL / FRIEND_INFLUX_TOKEN / FRIEND_INFLUX_ORG in env."
            )

        return InfluxDBClient(url=url, token=token, org=org)

    @staticmethod
    def fetch_room_state_df(*, room: str, days: int = 60) -> pd.DataFrame:
        bucket = os.getenv("FRIEND_INFLUX_BUCKET")
        org = os.getenv("FRIEND_INFLUX_ORG")

        if not bucket or not org:
            raise RuntimeError("Missing FRIEND_INFLUX_BUCKET / FRIEND_INFLUX_ORG in env.")

        start = _utc_now() - timedelta(days=days)

        flux = f"""
from(bucket: "{bucket}")
  |> range(start: {start.isoformat()})
  |> filter(fn: (r) => r._measurement == "state")
  |> filter(fn: (r) => r.entity_id == "{room}")
  |> keep(columns: ["_time","domain","entity_id","_field","_value"])
        """.strip()

        client = FriendInfluxDataset._get_client()
        query_api = client.query_api()

        tables = query_api.query_data_frame(flux)
        client.close()

        if tables is None:
            return pd.DataFrame()

        df = tables if not isinstance(tables, list) else pd.concat(tables, ignore_index=True)

        if df.empty:
            return df

        # normalize column names
        df = df.rename(columns={"_time": "time", "_value": "value", "_field": "field"})

        # ensure time is datetime
        df["time"] = pd.to_datetime(df["time"], utc=True)

        # drop null time
        df = df.dropna(subset=["time"])

        return df
