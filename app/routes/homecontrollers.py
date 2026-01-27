from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app import models, schemas, auth
from app.database import get_db
from app.core import homeassistant

router = APIRouter(prefix="/homecontrollers", tags=["homecontrollers"])


# API endpoint to set the state of a light
@router.post("/light", response_model=schemas.LightStateResponse)
async def set_light(
    light_state: schemas.LightState,
    current_user: models.User = Depends(auth.get_current_active_user),
):
    if light_state.state == "on":
        return await homeassistant.turn_on_light(light_state)
    else:
        return await homeassistant.turn_off_light(light_state)

@router.post("/device-control")
async def control_device_endpoint(
    device: schemas.DeviceControlRequest,
    current_user: models.User = Depends(auth.get_current_active_user),
):
    return await homeassistant.control_device(device)



@router.get("/devices", response_model=list[schemas.DeviceInfo])
async def list_devices(
    current_user: models.User = Depends(auth.get_current_active_user),
):
    return await homeassistant.get_all_devices()

@router.get('/current-state')
async def get_current_state(
    current_user: models.User = Depends(auth.get_current_active_user),
):
    return await homeassistant.get_current_state()

@router.get('/camera-snapshot')
async def get_camera_snapshot(
    camera_entity: str = Query(..., description="Camera entity ID (e.g., 'camera.frontdoor')"),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """
    Get a snapshot image from a Home Assistant camera.
    
    - **camera_entity**: The camera entity ID (e.g., "camera.frontdoor")
    
    Returns the image as a JPEG stream.
    """
    image_data, content_type = await homeassistant.get_camera_snapshot(camera_entity)
    
    if image_data is None:
        raise HTTPException(
            status_code=404,
            detail=f"Failed to retrieve camera snapshot for {camera_entity}"
        )
    
    return StreamingResponse(
        iter([image_data]),
        media_type=content_type or "image/jpeg",
        headers={
            "Content-Disposition": f"inline; filename={camera_entity.replace('.', '_')}.jpg"
        }
    )