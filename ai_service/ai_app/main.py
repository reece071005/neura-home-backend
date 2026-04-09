from contextlib import asynccontextmanager
from fastapi import FastAPI
import asyncio

from ai_app.routes.ai import router as ai_router
from ai_app.routes.influx import router as influx_router
from ai_app.core.ha_ws_listener import start_ha_websocket_listener, run_startup_snapshot
from ai_app.core.influxdb_init import init_influx, close_influx
from ai_app.services.automation_runner import automation_loop, retrain_loop


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_influx()

    await run_startup_snapshot()

    ws_task = asyncio.create_task(start_ha_websocket_listener())
    auto_task = asyncio.create_task(automation_loop(60))
    retrain_task = asyncio.create_task(retrain_loop())

    try:
        yield
    finally:
        ws_task.cancel()
        auto_task.cancel()
        retrain_task.cancel()

        for task in [ws_task, auto_task, retrain_task]:
            try:
                await task
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