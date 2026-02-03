import redis.asyncio as redis
from app.config import REDIS_URL


class RedisClient:
    """Singleton Redis client for the whole project."""

    _instance: "RedisClient | None" = None
    _client: redis.Redis | None = None

    def __new__(cls) -> "RedisClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    async def init_redis(cls) -> redis.Redis:
        """Create and store the Redis client. Call once at app startup."""
        if cls._client is not None:
            return cls._client
        cls._client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        return cls._client

    @classmethod
    def get_redis(cls) -> redis.Redis:
        """Return the shared Redis client. Raises RuntimeError if not initialized."""
        if cls._client is None:
            raise RuntimeError("Redis not initialized. Call init_redis() at app startup.")
        return cls._client

    @classmethod
    async def close_redis(cls) -> None:
        """Close the Redis connection. Call at app shutdown."""
        if cls._client is not None:
            await cls._client.aclose()
            cls._client = None



# Module-level API (delegate to singleton)
async def init_redis() -> redis.Redis:
    return await RedisClient.init_redis()


def get_redis() -> redis.Redis:
    return RedisClient.get_redis()


async def close_redis() -> None:
    await RedisClient.close_redis()

