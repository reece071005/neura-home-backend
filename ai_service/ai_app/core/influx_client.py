##not local for reece influx testing

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Iterable

from influxdb_client import InfluxDBClient
from influxdb_client.client.exceptions import InfluxDBError


@dataclass(frozen=True)
class InfluxConfig:
    url: str
    token: str
    org: str
    bucket: str
    source: str  # "local" or "ha"
    readonly: bool


def get_influx_config() -> InfluxConfig:
    url = os.getenv("INFLUX_URL", "http://influxdb:8086")
    token = os.getenv("INFLUX_TOKEN", "")
    org = os.getenv("INFLUX_ORG", "")
    bucket = os.getenv("INFLUX_BUCKET", "")

    source = os.getenv("INFLUX_SOURCE", "local").strip().lower()
    readonly = os.getenv("INFLUX_READONLY", "false").strip().lower() in {"1", "true", "yes", "y"}

    if not token or not org or not bucket:
        raise RuntimeError("Influx config missing. Ensure INFLUX_TOKEN, INFLUX_ORG, INFLUX_BUCKET are set.")

    if source not in {"local", "ha"}:
        raise RuntimeError("INFLUX_SOURCE must be 'local' or 'ha'.")

    return InfluxConfig(url=url, token=token, org=org, bucket=bucket, source=source, readonly=readonly)


class InfluxService:
    """
    Thin wrapper around influxdb-client.
    - query() returns list[dict] rows (easy to use in AI).
    - health() checks connectivity.
    """

    def __init__(self, cfg: InfluxConfig):
        self.cfg = cfg
        self._client = InfluxDBClient(url=cfg.url, token=cfg.token, org=cfg.org)

    def close(self) -> None:
        try:
            self._client.close()
        except Exception:
            pass

    def health(self) -> dict[str, Any]:
        try:
            healthy = self._client.ping()
            return {"ok": bool(healthy), "url": self.cfg.url, "org": self.cfg.org, "bucket": self.cfg.bucket, "source": self.cfg.source}
        except Exception as e:
            return {"ok": False, "error": str(e), "url": self.cfg.url, "org": self.cfg.org, "bucket": self.cfg.bucket, "source": self.cfg.source}

    def query(self, flux: str) -> list[dict[str, Any]]:
        """
        Returns rows as dicts with keys like:
          _time, _measurement, _field, _value, domain, entity_id, ...
        """
        api = self._client.query_api()
        try:
            tables = api.query(flux, org=self.cfg.org)
        except InfluxDBError as e:
            raise RuntimeError(f"Influx query failed: {e}") from e

        rows: list[dict[str, Any]] = []
        for table in tables:
            for record in table.records:
                rows.append(record.values)
        return rows


_influx_singleton: InfluxService | None = None


def get_influx() -> InfluxService:
    global _influx_singleton
    if _influx_singleton is None:
        cfg = get_influx_config()
        _influx_singleton = InfluxService(cfg)
    return _influx_singleton
