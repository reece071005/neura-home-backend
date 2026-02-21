from __future__ import annotations

import os
from functools import lru_cache
import redis.asyncio as redis


@lru_cache(maxsize=1)
def get_redis() -> redis.Redis:
    url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    return redis.from_url(url, decode_responses=True)
