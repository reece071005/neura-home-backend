"""
Vision service: FastAPI app for image analysis and optional camera surveillance.
Run as a separate container; no dependency on the main backend app.
"""
import asyncio
import base64
from contextlib import asynccontextmanager
from typing import Any

import cv2
import numpy as np
from fastapi import FastAPI, File, HTTPException, UploadFile

from config import load_home_assistant_config_from_db
from surveillance import run_surveillance


async def _periodic_reload_home_assistant_config(interval_seconds: int = 30) -> None:
    """
    Periodically reload Home Assistant URL/token from the database.

    Keeps the long-running vision service in sync with changes made by the API
    without any direct dependency between the two services.
    """
    while True:
        try:
            await load_home_assistant_config_from_db()
        except Exception:
            # On failure we just try again on the next interval.
            pass
        await asyncio.sleep(interval_seconds)


def _decode_upload(content: bytes) -> np.ndarray:
    nparr = np.frombuffer(content, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="Invalid or unsupported image format")
    return img


def _encode_image_bgr_to_base64_jpeg(image: np.ndarray) -> str:
    _, buf = cv2.imencode(".jpg", image)
    return base64.b64encode(buf.tobytes()).decode("ascii")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start surveillance if cameras are configured; cancel on shutdown."""
    # Initial load of Home Assistant configuration (URL + token) from DB
    try:
        await load_home_assistant_config_from_db()
    except Exception:
        # If config loading fails, we still start; surveillance will no-op if URL/headers missing.
        pass

    # Periodically refresh HA config in the background so credential/URL
    # changes are picked up without any cross-service calls.
    reload_task = asyncio.create_task(_periodic_reload_home_assistant_config())

    surveillance_task = None
    try:
        surveillance_task = await run_surveillance()
    except Exception:
        pass

    yield

    # Shutdown: cancel background tasks cleanly
    reload_task.cancel()
    try:
        await reload_task
    except asyncio.CancelledError:
        pass

    if surveillance_task is not None:
        surveillance_task.cancel()
        try:
            await surveillance_task
        except asyncio.CancelledError:
            pass


app = FastAPI(
    title="Neura Vision",
    description="Vision analysis and camera surveillance",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.post("/analyze")
async def analyze_image(
    file: UploadFile = File(..., description="Image file (JPEG/PNG) to analyze"),
    include_annotated: bool = True,
) -> dict[str, Any]:
    """
    Run the vision model on an uploaded image. Returns detections (person labels: RESIDENT, KID, DELIVERY, STRANGER)
    and optionally the annotated image as base64 JPEG for testing.
    """
    try:
        content = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read upload: {e}") from e

    img = _decode_upload(content)

    from camerastream import analyze_frame

    loop = asyncio.get_running_loop()
    try:
        annotated, detections = await loop.run_in_executor(None, analyze_frame, img)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis failed: {e}") from e

    out: dict[str, Any] = {
        "detections": detections,
        "count": len(detections),
    }
    if include_annotated and annotated is not None:
        out["annotated_image_base64"] = _encode_image_bgr_to_base64_jpeg(annotated)
    return out
