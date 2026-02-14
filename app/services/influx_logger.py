from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional

from influxdb_client import Point, WritePrecision
from app.core.influxdb_init import get_influx_write_api
import os


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class InfluxLogger:
    @staticmethod
    def log_device_state(
        *,
        entity_id: str,
        domain: str,
        state: Optional[str],
        attributes: Optional[Dict[str, Any]] = None,
        area: Optional[str] = None,
        source: str = "snapshot",
        ts: Optional[datetime] = None,
    ) -> None:
        bucket = os.getenv("INFLUX_BUCKET", "smart_home")
        org = os.getenv("INFLUX_ORG", "neura")

        ts = ts or _now_utc()
        attributes = attributes or {}

        point = (
            Point("device_state")
            .tag("entity_id", entity_id)
            .tag("domain", domain)
            .tag("source", source)
        )

        if area:
            point = point.tag("area", area)

        if state is not None:
            point = point.field("state", str(state))

        for k in ["brightness", "temperature", "humidity", "power", "energy", "percentage", "position"]:
            v = attributes.get(k)
            if isinstance(v, (int, float)):
                point = point.field(k, float(v))

        try:
            import json
            point = point.field("attributes_json", json.dumps(attributes)[:20000])
        except Exception:
            point = point.field("attributes_json", "{}")

        point = point.time(ts, WritePrecision.NS)

        write_api = get_influx_write_api()
        write_api.write(bucket=bucket, org=org, record=point)

    @staticmethod
    def log_user_action(
        *,
        user_id: int,
        entity_id: str,
        domain: str,
        action: str,
        value: Optional[float] = None,
        meta: Optional[Dict[str, Any]] = None,
        ts: Optional[datetime] = None,
    ) -> None:
        bucket = os.getenv("INFLUX_BUCKET", "smart_home")
        org = os.getenv("INFLUX_ORG", "neura")

        ts = ts or _now_utc()
        meta = meta or {}

        point = (
            Point("user_action")
            .tag("user_id", str(user_id))
            .tag("entity_id", entity_id)
            .tag("domain", domain)
            .tag("action", action)
        )

        if value is not None:
            point = point.field("value", float(value))
        else:
            point = point.field("value", 0.0)

        try:
            import json
            point = point.field("meta_json", json.dumps(meta)[:20000])
        except Exception:
            point = point.field("meta_json", "{}")

        point = point.time(ts, WritePrecision.NS)

        write_api = get_influx_write_api()
        write_api.write(bucket=bucket, org=org, record=point)
