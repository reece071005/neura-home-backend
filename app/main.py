from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from app.database import engine, Base
from app.routes import (
    auth,
    users,
    homecontrollers,
    voice,
    userfaces,
    vision,
    hub,
    rooms,
    automation,
    demo_time,
)
from app.routes import ai_proxy

from app.core.redis_init import init_redis, close_redis
from app.core.cache_management import CacheManagement
from app.config import load_home_assistant_config_from_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:  # type: AsyncEngine
        await conn.run_sync(Base.metadata.create_all)

    await load_home_assistant_config_from_db()
    await init_redis()
    await CacheManagement.update_cache()

    yield

    await close_redis()


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
app.include_router(userfaces.router)
app.include_router(vision.router)
app.include_router(hub.router)
app.include_router(rooms.router)
app.include_router(ai_proxy.router)
app.include_router(automation.router)
app.include_router(demo_time.router)


@app.get("/")
async def read_root():
    return {"message": "Welcome to Neura API"}


@app.get("/health")
async def health_check():
    return {"status": "healthy"}