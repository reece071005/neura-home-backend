import os

HOME_ASSISTANT_URL = "https://70i5piqxrwxbmwtnseu92fpobavxtcpe.ui.nabu.casa/api"
ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJjOTU0NGZmOTVmNTg0NDU4YThhYjRkMzc2NDc4YzRkYSIsImlhdCI6MTc2ODMyMDI5MiwiZXhwIjoyMDgzNjgwMjkyfQ.d6JJi6e4lSOj8dJMIRul3ce32E10t4bzb-VKIZlFRoM"
HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json",
}

REDIS_URL = "redis://redis:6379/0"
LLM_KEY = "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"

# Vision notify folder (shared with vision container; mount vision_notify to this path)
NOTIFY_DIR = os.getenv("NOTIFY_DIR", "/app/notify")