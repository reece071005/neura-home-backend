##this is gor the user action logging from the main backend to ai service
from __future__ import annotations

import os
import aiohttp


AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://ai_service:8002")


async def log_user_action_to_ai_service(
    *,
    user_id: int,
    entity_id: str,
    domain: str,
    action: str,
    value: float | None = None,
    meta: dict | None = None,
) -> None:
    payload = {
        "user_id": user_id,
        "entity_id": entity_id,
        "domain": domain,
        "action": action,
        "value": value,
        "meta": meta or {},
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{AI_SERVICE_URL}/influx/log-action", json=payload) as resp:
                if resp.status >= 400:
                    text = await resp.text()
                    print(f"[AI_ACTION_LOG] Failed: status={resp.status}, body={text}")
    except Exception as e:
        print(f"[AI_ACTION_LOG] Exception while logging user action: {e}")