import aiohttp

import os

AI_SERVICE_URL = os.getenv("AI_SERVICE_URL", "http://ai_service:8002")

async def call_ai(endpoint: str, method="GET", params=None, json=None):
    async with aiohttp.ClientSession() as session:
        async with session.request(
            method,
            f"{AI_SERVICE_URL}{endpoint}",
            params=params,
            json=json,
        ) as resp:
            return await resp.json()
