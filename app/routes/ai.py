from fastapi import APIRouter, Depends, Query
from app import auth, models

from app.ai.recommender import Recommender
from app.ai.room_trainer import RoomTrainer

router = APIRouter(prefix="/ai", tags=["AI"])


@router.post("/train")
async def train_ai(
    window_hours: int = Query(24 * 14, ge=24, le=24 * 365),
    current_admin: models.User = Depends(auth.get_current_admin_user),
):
    return Recommender.train_behavior_profile(window_hours=window_hours)


@router.get("/recommendations")
async def get_recommendations(
    current_user: models.User = Depends(auth.get_current_active_user),
):
    return Recommender.recommend_for_user(user_id=current_user.id)



# training from Reeces data


@router.post("/train-room")
async def train_room(
    room: str,
    days: int = 60,
    current_admin: models.User = Depends(auth.get_current_admin_user),
):
    return RoomTrainer.train_room(room=room, days=days)
