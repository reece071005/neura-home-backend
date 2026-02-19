import os

HOME_ASSISTANT_URL = "https://70i5piqxrwxbmwtnseu92fpobavxtcpe.ui.nabu.casa/api"
ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJjOTU0NGZmOTVmNTg0NDU4YThhYjRkMzc2NDc4YzRkYSIsImlhdCI6MTc2ODMyMDI5MiwiZXhwIjoyMDgzNjgwMjkyfQ.d6JJi6e4lSOj8dJMIRul3ce32E10t4bzb-VKIZlFRoM"
HA_HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json",
}

RESIDENTS_DIR = os.getenv("VISION_RESIDENTS_DIR", "/app/residents")
VISION_NOTIFY_DIR = os.getenv("NOTIFY_DIR", "/app/notify")

VISION_INTERVAL_SECONDS = int(os.getenv("VISION_INTERVAL_SECONDS", "5"))

VISION_DATABASE_URL = os.getenv(
    "VISION_DATABASE_URL",
    "postgresql://postgres:postgres@db:5432/neura_db",
)

API_URL = "http://api.neura-home-backend.orb.local:8000"