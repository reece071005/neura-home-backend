from contextlib import asynccontextmanager
from fastapi import FastAPI
import asyncio

from ai_app.routes.ai import router as ai_router
from ai_app.routes.influx import router as influx_router
from ai_app.core.ha_ws_listener import start_ha_websocket_listener, run_startup_snapshot
from ai_app.core.influxdb_init import init_influx, close_influx
from ai_app.services.automation_runner import automation_loop, retrain_loop


async def run_startup_snapshot_with_retry(max_attempts: int = 12, delay_seconds: int = 5):
    for attempt in range(1, max_attempts + 1):
        try:
            print(f"[WS] Startup snapshot attempt {attempt}/{max_attempts}")
            await run_startup_snapshot()
            return
        except Exception as e:
            print(f"[WS] Startup snapshot attempt {attempt} failed: {e}")
            if attempt < max_attempts:
                await asyncio.sleep(delay_seconds)

    print("[WS] Startup snapshot failed after all retries.")

async def periodic_snapshot_loop(interval_seconds: int = 300):
    while True:
        await asyncio.sleep(interval_seconds)

        try:
            print("[WS] Running periodic snapshot...")
            await run_startup_snapshot()
            print("[WS] Periodic snapshot completed.")
        except Exception as e:
            print(f"[WS] Periodic snapshot failed: {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_influx()

    await run_startup_snapshot_with_retry()

    ws_task = asyncio.create_task(start_ha_websocket_listener())
    auto_task = asyncio.create_task(automation_loop(60))
    retrain_task = asyncio.create_task(retrain_loop())
    snapshot_task = asyncio.create_task(periodic_snapshot_loop(300))

    try:
        yield
    finally:
        ws_task.cancel()
        auto_task.cancel()
        retrain_task.cancel()

        for task in [ws_task, auto_task, retrain_task, snapshot_task]:
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