import os
from typing import Optional
import json
import asyncpg
import hashlib
import base64
from cryptography.fernet import Fernet


HOME_ASSISTANT_URL: Optional[str] = os.getenv("HOME_ASSISTANT_URL")
ACCESS_TOKEN: Optional[str] = os.getenv("HOME_ASSISTANT_ACCESS_TOKEN")

HA_HEADERS: dict[str, str] = {}
if ACCESS_TOKEN:
    HA_HEADERS["Authorization"] = f"Bearer {ACCESS_TOKEN}"
HA_HEADERS.setdefault("Content-Type", "application/json")


RESIDENTS_DIR = os.getenv("VISION_RESIDENTS_DIR", "/app/residents")
VISION_NOTIFY_DIR = os.getenv("NOTIFY_DIR", "/app/notify")

VISION_INTERVAL_SECONDS = int(os.getenv("VISION_INTERVAL_SECONDS", "5"))

VISION_DATABASE_URL = os.getenv(
    "VISION_DATABASE_URL",
    "postgresql://postgres:postgres@db:5432/neura_db",
)
SECRET_KEY = os.getenv("SECRET_KEY", "1a596c46af920d405709d28bc83c5d80491910d531ae34af4e804e853d0458b4")

def _get_fernet() -> Fernet:
    """Derive a Fernet key from the application's SECRET_KEY."""
    digest = hashlib.sha256(SECRET_KEY.encode("utf-8")).digest()
    fernet_key = base64.urlsafe_b64encode(digest)
    return Fernet(fernet_key)

async def load_home_assistant_config_from_db() -> None:
    """
    Load Home Assistant URL and secret from the `configurations` table
    using asyncpg and VISION_DATABASE_URL.

    Expects rows like:
      - key = 'home_assistant_url', value = "<base_api_url>"
      - key = 'home_assistant_secret', value = {"ciphertext": "<encrypted_token>"} or "<plain_token>"
    """
    global HOME_ASSISTANT_URL, ACCESS_TOKEN, HA_HEADERS
    print(f"Loading home assistant config from database: {VISION_DATABASE_URL}")
    if not VISION_DATABASE_URL:
        return

    print(f"Connecting to database: {VISION_DATABASE_URL}")
    try:
        conn = await asyncpg.connect(VISION_DATABASE_URL)
    except Exception:
        return

    print(f"Fetching rows from database: {VISION_DATABASE_URL}")
    try:
        rows = await conn.fetch(
            """
            SELECT key, value
            FROM configurations
            WHERE key = ANY($1::text[])
            """,
            ["home_assistant_url", "home_assistant_secret"],
        )
    except Exception:
        await conn.close()
        return

    print(f"Closing database connection: {VISION_DATABASE_URL}")
    await conn.close()

    config_map: dict[str, str] = {}
    for row in rows:
        key = row["key"]
        raw_value = row["value"]
        print(key, raw_value)
        parsed: Optional[str] = None
        print(f"Key: {key}, Raw Value: {raw_value}")
        if key == "home_assistant_url":
            raw_value = json.loads(raw_value)['url']
            parsed = raw_value
        elif key == "home_assistant_secret":
            raw_value = json.loads(raw_value)['ciphertext']
            print(f"Decrypting Home Assistant Access Token: {raw_value}")
            f = _get_fernet()
            parsed = f.decrypt(raw_value.encode("utf-8")).decode("utf-8")
            print(f"Decrypted Home Assistant Access Token: {parsed}")

        if parsed is not None:
            config_map[key] = parsed
    print(f"Config Map: {config_map}")
    if "home_assistant_url" in config_map:
        HOME_ASSISTANT_URL = config_map["home_assistant_url"]
    if "home_assistant_secret" in config_map:
        ACCESS_TOKEN = config_map["home_assistant_secret"]
        print(f"Setting Home Assistant Access Token: {ACCESS_TOKEN}")

    # print(f"Setting Home Assistant URL: {HOME_ASSISTANT_URL}")
    # print(f"Setting Home Assistant Access Token: {ACCESS_TOKEN}")

    HA_HEADERS = {}
    if ACCESS_TOKEN:
        HA_HEADERS["Authorization"] = f"Bearer {ACCESS_TOKEN}"
    HA_HEADERS["Content-Type"] = "application/json"
    print(f"HA_HEADERS: {HA_HEADERS}")
