from fastapi import APIRouter, Depends, Query
from app.services.ai_client import call_ai
from app import auth, models

router = APIRouter(prefix="/ai", tags=["AI"])

@router.get("/rooms")
async def rooms(current_user: models.User = Depends(auth.get_current_active_user)):
    return await call_ai("/ai/rooms")

@router.get("/suggestion-cards")
async def suggestion_cards(room: str, current_user: models.User = Depends(auth.get_current_active_user)):
    return await call_ai("/ai/suggestion-cards", params={"room": room})

@router.get("/smart-suggestions")
async def smart_suggestions(room: str, current_user: models.User = Depends(auth.get_current_active_user)):
    return await call_ai("/ai/smart-suggestions", params={"room": room})

@router.post("/train-room-xgb")
async def train_room(room: str, days: int = 60, current_admin: models.User = Depends(auth.get_current_admin_user)):
    return await call_ai("/ai/train-room-xgb", method="POST", params={"room": room, "days": days})
