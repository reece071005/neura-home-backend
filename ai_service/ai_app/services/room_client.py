import os
import aiohttp

APP_URL = os.getenv("APP_URL", "http://api:8000")

async def fetch_all_rooms():
    async with aiohttp.ClientSession() as session:
        async with session.get(f"{APP_URL}/rooms/internal/all") as resp:
            resp.raise_for_status()
            return await resp.json()