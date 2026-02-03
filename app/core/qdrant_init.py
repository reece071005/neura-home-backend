# app/core/qdrant_init.py
"""Singleton Qdrant client for the whole project."""

from qdrant_client import AsyncQdrantClient

from app.config import QDRANT_URL

_client: AsyncQdrantClient | None = None


async def init_qdrant() -> AsyncQdrantClient:
    """Create and store the Qdrant client. Call once at app startup."""
    global _client
    if _client is not None:
        return _client
    _client = AsyncQdrantClient(url=QDRANT_URL)
    return _client


def get_qdrant() -> AsyncQdrantClient:
    """Return the shared Qdrant client. Raises RuntimeError if not initialized."""
    if _client is None:
        raise RuntimeError("Qdrant not initialized. Call init_qdrant() at app startup.")
    return _client


async def close_qdrant() -> None:
    """Release the Qdrant client. Call at app shutdown."""
    global _client
    if _client is not None:
        await _client.close()
        _client = None
