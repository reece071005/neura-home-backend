from contextlib import asynccontextmanager
from fastapi import FastAPI
import asyncio

from ai_app.routes.ai import router as ai_router
from ai_app.routes.influx import router as influx_router
from ai_app.core.ha_ws_listener import start_ha_websocket_listener
from ai_app.core.influxdb_init import init_influx, close_influx
from ai_app.services.automation_runner import automation_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_influx()

    ws_task = asyncio.create_task(start_ha_websocket_listener())
    auto_task = asyncio.create_task(automation_loop(60))

    try:
        yield
    finally:
        ws_task.cancel()
        auto_task.cancel()

        try:
            await ws_task
        except asyncio.CancelledError:
            pass

        try:
            await auto_task
        except asyncio.CancelledError:
            pass

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