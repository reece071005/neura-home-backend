from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app import models, schemas, auth
from app.database import get_db
from app.core.homeassistant import LightControl, DeviceControl, CameraControl, CoverControl, ClimateControl, FanControl

router = APIRouter(prefix="/homecontrollers", tags=["homecontrollers"])


# API endpoint to set the state of a light
@router.post("/light", response_model=schemas.LightStateResponse)
async def set_light(
    light_state: schemas.LightState,
    current_user: models.User = Depends(auth.get_current_active_user),
):
    if light_state.state == "on":
        return await LightControl.turn_on_light(light_state)
    else:
        return await LightControl.turn_off_light(light_state)

@router.post("/cover", response_model=schemas.CoverStateResponse)
async def set_cover_position(
    cover_state: schemas.CoverState,
    current_user: models.User = Depends(auth.get_current_active_user),
):
    return await CoverControl.set_cover_position(cover_state.entity_id, cover_state.position)

@router.post("/climate", response_model=schemas.ClimateStateResponse)
async def set_climate_state(
    climate_state: schemas.ClimateState,
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """
    - **entity_id**: The climate entity ID (e.g., "climate.livingroom")
    - **state**: "on" / "off"
    - **temperature**: Target temperature in °C (e.g., 22.0)
    - **hvac_mode**: HVAC mode (e.g., "heat", "cool", "heat_cool", "auto", "off")
    - **fan_mode**: Fan mode (e.g., "low", "medium", "high")
    - **swing_mode**: Swing mode (e.g., "on"/"off")
    - **swing_horizontal_mode**: Swing horizontal mode (e.g., "on"/"off")
    """
    return await ClimateControl.control_climate(climate_state.entity_id, climate_state.state, climate_state.hvac_mode, climate_state.temperature, climate_state.fan_mode, climate_state.swing_mode, climate_state.swing_horizontal_mode)

@router.post("/fan", response_model=schemas.FanStateResponse)
async def set_fan_state(
    fan_state: schemas.FanState,
    current_user: models.User = Depends(auth.get_current_active_user),
):
    return await FanControl.control_fan(fan_state.entity_id, fan_state.state, fan_state.percentage,fan_state.oscillating, fan_state.direction)
@router.post("/device-control")
async def control_device_endpoint(
    device: schemas.DeviceControlRequest,
    current_user: models.User = Depends(auth.get_current_active_user),
):
    return await DeviceControl.control_device(device)


@router.get("/devices", response_model=list[schemas.DeviceInfo])
async def list_devices(
    current_user: models.User = Depends(auth.get_current_active_user),
):
    return await DeviceControl.get_all_devices()

@router.get('/current-state')
async def get_current_state(
    current_user: models.User = Depends(auth.get_current_active_user),
):
    return await DeviceControl.get_current_state()

@router.get('/current-state-device')
async def get_current_state_device(
    entity_id: str = Query(..., description="Device entity ID (e.g., 'light.livingroom')"),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    return await DeviceControl.get_current_state_device(entity_id)

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
    image_data, content_type = await CameraControl.get_camera_snapshot(camera_entity)
    
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