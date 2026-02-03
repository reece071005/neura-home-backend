import os

HOME_ASSISTANT_URL = "https://70i5piqxrwxbmwtnseu92fpobavxtcpe.ui.nabu.casa/api"
ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJjOTU0NGZmOTVmNTg0NDU4YThhYjRkMzc2NDc4YzRkYSIsImlhdCI6MTc2ODMyMDI5MiwiZXhwIjoyMDgzNjgwMjkyfQ.d6JJi6e4lSOj8dJMIRul3ce32E10t4bzb-VKIZlFRoM"
HEADERS = {
    "Authorization": f"Bearer {ACCESS_TOKEN}",
    "Content-Type": "application/json",
}

REDIS_URL = "redis://redis:6379/0"

# Ollama embedding model for device matching (run: ollama pull <model>)
EMBED_MODEL = os.getenv("EMBED_MODEL", "nomic-embed-text")
EMBED_API_URL = os.getenv("EMBED_API_URL", "http://host.docker.internal:11434/api/embeddings")

# Qdrant vector DB (default: local)
QDRANT_URL = os.getenv("QDRANT_URL", "http://qdrant:6333")
QDRANT_COLLECTION_NAME = "home_commands_v2"