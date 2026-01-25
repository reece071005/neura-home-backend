from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app import models, schemas, auth
from app.database import get_db
from app.core import homeassistant

router = APIRouter(prefix="/homecontrollers", tags=["homecontrollers"])


# API endpoint to set the state of a light
@router.post("/turn-on-light", response_model=schemas.LightStateResponse)
async def turn_on_light_api(
    light_state: schemas.LightState,
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """Turn on a light"""
    return await homeassistant.turn_on_light(light_state)

# API endpoint to turn off a light
@router.post("/turn-off-light", response_model=schemas.LightStateResponse)
async def turn_off_light_api(
    light_state: schemas.LightState,
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """Turn off a light"""
    return await homeassistant.turn_off_light(light_state)