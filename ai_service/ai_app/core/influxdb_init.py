from __future__ import annotations

import os
from typing import Optional

from influxdb_client import InfluxDBClient
from influxdb_client.client.influxdb_client_async import InfluxDBClientAsync
from influxdb_client.client.write_api import SYNCHRONOUS


class InfluxClient:
    """
    Provides BOTH:
    - sync client for the current training/query/logger code
    - async client for endpoints that want async ping/access

    This fixes the previous mismatch where several files called query/write
    APIs synchronously while the init layer exposed async-only accessors.
    """

    _sync_client: Optional[InfluxDBClient] = None
    _async_client: Optional[InfluxDBClientAsync] = None

    @classmethod
    def _config(cls) -> tuple[str, str, str]:
        url = os.getenv("INFLUX_URL", "http://influxdb:8086")
        token = os.getenv("INFLUX_TOKEN", "")
        org = os.getenv("INFLUX_ORG", "neura")

        if not token:
            raise RuntimeError("INFLUX_TOKEN is missing.")

        return url, token, org

    @classmethod
    async def init_influx(cls):
        url, token, org = cls._config()

        if cls._sync_client is None:
            cls._sync_client = InfluxDBClient(url=url, token=token, org=org)

        if cls._async_client is None:
            cls._async_client = InfluxDBClientAsync(url=url, token=token, org=org)

        return cls._async_client

    @classmethod
    def get_sync_client(cls) -> InfluxDBClient:
        if cls._sync_client is None:
            url, token, org = cls._config()
            cls._sync_client = InfluxDBClient(url=url, token=token, org=org)
        return cls._sync_client

    @classmethod
    async def get_async_client(cls) -> InfluxDBClientAsync:
        if cls._async_client is None:
            url, token, org = cls._config()
            cls._async_client = InfluxDBClientAsync(url=url, token=token, org=org)
        return cls._async_client

    @classmethod
    def get_write_api(cls):
        client = cls.get_sync_client()
        return client.write_api(write_options=SYNCHRONOUS)

    @classmethod
    def get_query_api(cls):
        client = cls.get_sync_client()
        return client.query_api()

    @classmethod
    async def close_influx(cls) -> None:
        if cls._async_client is not None:
            await cls._async_client.close()
            cls._async_client = None

        if cls._sync_client is not None:
            cls._sync_client.close()
            cls._sync_client = None


# ============================================
# BACKWARD COMPATIBILITY FUNCTIONS
# ============================================

def init_influx():
    return InfluxClient.init_influx()


async def get_influx_client():
    return await InfluxClient.get_async_client()


def get_influx_write_api():
    return InfluxClient.get_write_api()


def get_influx_query_api():
    return InfluxClient.get_query_api()


def close_influx():
    return InfluxClient.close_influx()