import os
from typing import Optional

from sqlalchemy import select

from app.database import SessionLocal
from app.models import Configuration
from app.core.encryption import decrypt_secret


# Home Assistant configuration
# Defaults are loaded from environment; they can be overridden from DB on startup.
HOME_ASSISTANT_URL: Optional[str] = os.getenv("HOME_ASSISTANT_URL")
ACCESS_TOKEN: Optional[str] = os.getenv("HOME_ASSISTANT_ACCESS_TOKEN")

HEADERS: dict[str, str] = {}
if ACCESS_TOKEN:
    HEADERS["Authorization"] = f"Bearer {ACCESS_TOKEN}"
# HOME_ASSISTANT_URL = "https://70i5piqxrwxbmwtnseu92fpobavxtcpe.ui.nabu.casa/api"
# ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJjOTU0NGZmOTVmNTg0NDU4YThhYjRkMzc2NDc4YzRkYSIsImlhdCI6MTc2ODMyMDI5MiwiZXhwIjoyMDgzNjgwMjkyfQ.d6JJi6e4lSOj8dJMIRul3ce32E10t4bzb-VKIZlFRoM"
# HA_HEADERS = {
#     "Authorization": f"Bearer {ACCESS_TOKEN}",
#     "Content-Type": "application/json",
# }


async def load_home_assistant_config_from_db() -> None:
    """
    Load Home Assistant URL and secret from the `configurations` table.

    Expects rows like:
      - key = 'home_assistant_url', value = "<base_api_url>"
      - key = 'home_assistant_secret', value = "<long_lived_secret>"
    """
    global HOME_ASSISTANT_URL, ACCESS_TOKEN, HEADERS

    async with SessionLocal() as session:
        result = await session.execute(
            select(Configuration).where(
                Configuration.key.in_(
                    ["home_assistant_url", "home_assistant_secret"]
                )
            )
        )
        rows = result.scalars().all()

    config_map: dict[str, str] = {}
    for row in rows:
        raw_value = row.value

        parsed: Optional[str] = None
        if isinstance(raw_value, str):
            parsed = raw_value
        elif isinstance(raw_value, dict):
            if "value" in raw_value and isinstance(raw_value["value"], str):
                parsed = raw_value["value"]
            elif "url" in raw_value and isinstance(raw_value["url"], str):
                parsed = raw_value["url"]
            elif "ciphertext" in raw_value and isinstance(raw_value["ciphertext"], str):
                parsed = decrypt_secret(raw_value["ciphertext"])

        if parsed is not None:
            config_map[row.key] = parsed

    if "home_assistant_url" in config_map:
        HOME_ASSISTANT_URL = config_map["home_assistant_url"]
    if "home_assistant_secret" in config_map:
        ACCESS_TOKEN = config_map["home_assistant_secret"]
    # Rebuild headers based on the latest token
    HEADERS = {}
    if ACCESS_TOKEN:
        HEADERS["Authorization"] = f"Bearer {ACCESS_TOKEN}"
    HEADERS["Content-Type"] = "application/json"


# Redis and other global config
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")
LLM_KEY = "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"

# Vision notify folder (shared with vision container; mount vision_notify to this path)
NOTIFY_DIR = os.getenv("NOTIFY_DIR", "/app/notify")