from fastapi import FastAPI
from ai_app.routes.ai import router as ai_router
from ai_app.routes.influx import router as influx_router
from contextlib import asynccontextmanager
from ai_app.core.ha_ws_listener import start_ha_websocket_listener
from ai_app.core.influxdb_init import init_influx, close_influx

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_influx()
    await start_ha_websocket_listener()
    yield
    await close_influx()

app = FastAPI(
    title="Neura AI Service",
    version="1.0.0",
    lifespan=lifespan
)
app.include_router(ai_router)
app.include_router(influx_router)
@app.get("/health")
async def health():
    return {"status": "AI healthy"}
