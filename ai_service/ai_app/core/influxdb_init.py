from __future__ import annotations

import os
from functools import lru_cache
from influxdb_client import InfluxDBClient


@lru_cache(maxsize=1)
def get_influx_client() -> InfluxDBClient:
    url = os.getenv("INFLUX_URL")
    token = os.getenv("INFLUX_TOKEN")
    org = os.getenv("INFLUX_ORG")

    if not url or not token or not org:
        raise RuntimeError("Missing INFLUX_URL / INFLUX_TOKEN / INFLUX_ORG in ai_service env.")

    return InfluxDBClient(url=url, token=token, org=org)


def get_influx_query_api():
    return get_influx_client().query_api()
