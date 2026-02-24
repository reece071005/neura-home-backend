from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from app.database import engine, Base
from app.routes import auth, users, homecontrollers, voice
from app.routes import influx as influx_routes
from app.routes import ai_proxy

from app.core.redis_init import init_redis, close_redis
from app.core.cache_management import CacheManagement
from app.core.qdrant_init import init_qdrant, close_qdrant
from app.core.influxdb_init import init_influx, close_influx
from app.routes import automation


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    await init_redis()
    await init_qdrant()
    await CacheManagement.update_cache()
    init_influx()

    yield

    close_influx()
    await close_redis()
    await close_qdrant()


app = FastAPI(
    title="Neura API",
    version="1.0.0",
    lifespan=lifespan
)

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(homecontrollers.router)
app.include_router(voice.router)
app.include_router(influx_routes.router)
app.include_router(ai_proxy.router)
app.include_router(automation.router)
@app.get("/")
async def read_root():
    return {"message": "Welcome to Neura API"}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
