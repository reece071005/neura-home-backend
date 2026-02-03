from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from app.database import engine, Base
from app.routes import auth, users, homecontrollers, voice
from app.core.redis_init import init_redis, close_redis
from app.core.cache_management import CacheManagement
from app.core.qdrant_init import init_qdrant, close_qdrant

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context to handle startup/shutdown tasks."""
    # Run DB migrations / create tables on startup
    async with engine.begin() as conn:  # type: AsyncEngine
        await conn.run_sync(Base.metadata.create_all)
    # Initialize Redis client (single instance for the whole app)
    await init_redis()
    await init_qdrant()
    await CacheManagement.update_cache()
    yield
    await close_redis()
    await close_qdrant()


app = FastAPI(
    title="Neura API",
    description="FastAPI application with voice assistant integration",
    version="1.0.0",
    lifespan=lifespan
)
app.include_router(auth.router)
app.include_router(users.router)
app.include_router(homecontrollers.router)
app.include_router(voice.router)
@app.get("/")
async def read_root():
    return {"message": "Welcome to Neura API"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
