import os
from typing import Optional

from influxdb_client import InfluxDBClient
from influxdb_client.client.write_api import SYNCHRONOUS


# ============================================
# LOCAL INFLUX CLIENT (YOUR SYSTEM)
# ============================================

class InfluxClient:
    _client: Optional[InfluxDBClient] = None

    @classmethod
    def init_influx(cls) -> InfluxDBClient:
        if cls._client is not None:
            return cls._client

        url = os.getenv("INFLUX_URL", "http://localhost:8086")
        token = os.getenv("INFLUX_TOKEN", "")
        org = os.getenv("INFLUX_ORG", "neura")

        if not token:
            raise RuntimeError("INFLUX_TOKEN is missing.")

        cls._client = InfluxDBClient(url=url, token=token, org=org)
        return cls._client

    @classmethod
    def get_client(cls) -> InfluxDBClient:
        if cls._client is None:
            raise RuntimeError("InfluxDB not initialized. Call init_influx() at startup.")
        return cls._client

    @classmethod
    def get_write_api(cls):
        return cls.get_client().write_api(write_options=SYNCHRONOUS)

    @classmethod
    def get_query_api(cls):
        return cls.get_client().query_api()

    @classmethod
    def close_influx(cls) -> None:
        if cls._client is not None:
            cls._client.close()
            cls._client = None


# ============================================
# FRIEND INFLUX CLIENT (READ ONLY)
# ============================================

class FriendInfluxClient:
    _client: Optional[InfluxDBClient] = None

    @classmethod
    def get_client(cls) -> InfluxDBClient:
        if cls._client is not None:
            return cls._client

        url = os.getenv("FRIEND_INFLUX_URL")
        token = os.getenv("FRIEND_INFLUX_TOKEN")
        org = os.getenv("FRIEND_INFLUX_ORG")

        if not all([url, token, org]):
            raise RuntimeError("Friend Influx environment variables are missing.")

        cls._client = InfluxDBClient(url=url, token=token, org=org)
        return cls._client

    @classmethod
    def get_query_api(cls):
        return cls.get_client().query_api()


# ============================================
# BACKWARD COMPATIBILITY FUNCTIONS
# (So your main.py does not break)
# ============================================

def init_influx():
    return InfluxClient.init_influx()


def get_influx_client():
    return InfluxClient.get_client()


def get_influx_write_api():
    return InfluxClient.get_write_api()


def get_influx_query_api():
    return InfluxClient.get_query_api()


def close_influx():
    InfluxClient.close_influx()
