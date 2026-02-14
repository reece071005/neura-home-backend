from datetime import datetime, timedelta, timezone
import os
import pandas as pd

from app.core.influxdb_init import FriendInfluxClient


def _utc_now():
    return datetime.now(timezone.utc)


class FriendInfluxDataset:

    @staticmethod
    def fetch_room_state_df(room: str, days: int = 60) -> pd.DataFrame:
        bucket = os.getenv("FRIEND_INFLUX_BUCKET")
        start = _utc_now() - timedelta(days=days)

        flux = f"""
from(bucket: "{bucket}")
  |> range(start: {start.isoformat()})
  |> filter(fn: (r) => r._measurement == "state")
  |> filter(fn: (r) => r.entity_id == "{room}")
  |> keep(columns: ["_time","domain","entity_id","_field","_value"])
        """

        query_api = FriendInfluxClient.get_query_api()
        tables = query_api.query_data_frame(flux)

        if tables is None or (isinstance(tables, list) and len(tables) == 0):
            return pd.DataFrame()

        df = tables if not isinstance(tables, list) else pd.concat(tables, ignore_index=True)
        if df.empty:
            return df

        df = df.rename(columns={"_time": "time"})
        return df
