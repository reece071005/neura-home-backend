import os
from typing import Optional
from influxdb_client import InfluxDBClient
from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
from influxdb_client.client.write_api import SYNCHRONOUS


# ============================================
# LOCAL INFLUX CLIENT (YOUR SYSTEM)
# ============================================

class InfluxClient:
    _client: Optional[InfluxDBClientAsync] = None

    @classmethod
    async def init_influx(cls) -> InfluxDBClientAsync:
        if cls._client is not None:
            return cls._client
        print('CREATING INFLUX CLIENT')
        url = os.getenv("INFLUX_URL", "http://localhost:8086")
        token = os.getenv("INFLUX_TOKEN", "")
        org = os.getenv("INFLUX_ORG", "neura")

        if not token:
            raise RuntimeError("INFLUX_TOKEN is missing.")

        cls._client = InfluxDBClientAsync(url=url, token=token, org=org)
        return cls._client

    @classmethod
    async def get_client(cls) -> InfluxDBClientAsync:
        if cls._client is None:
            raise RuntimeError("InfluxDB not initialized. Call init_influx() at startup.")
        return cls._client

    @classmethod
    async def get_write_api(cls):
        client = await cls.get_client()
        return client.write_api()

    @classmethod
    async def get_query_api(cls):
        client = await cls.get_client()
        return client.query_api()

    @classmethod
    async def close_influx(cls) -> None:
        if cls._client is not None:
            await cls._client.close()
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
    return InfluxClient.close_influx()
