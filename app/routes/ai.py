from __future__ import annotations

from datetime import datetime
from fastapi import APIRouter, Depends, Query, HTTPException
from app import auth, models

from app.ai.room_trainer import RoomTrainer


router = APIRouter(prefix="/ai", tags=["AI"])


@router.post("/train-room")
async def train_room(
    room: str = Query(..., description="Room entity_id like guest_room, kitchen, reece_room"),
    days: int = Query(60, ge=1, le=365),
    current_admin: models.User = Depends(auth.get_current_admin_user),
):
    return RoomTrainer.train_room(room=room, days=days)



@router.get("/predict-room")
async def predict_room(
    room: str = Query(...),
    hour: int = Query(..., ge=0, le=23),
    threshold: float = Query(0.25, ge=0.0, le=1.0),
    current_user: models.User = Depends(auth.get_current_active_user),
):

    now = datetime.utcnow()
    is_weekend = now.weekday() >= 5
    day_type = "weekend" if is_weekend else "weekday"

    domains_to_check = ["light", "climate", "cover", "fan"]
    actions = []

    for domain in domains_to_check:
        profile = RoomTrainer.load_profile(room=room, domain=domain)
        if not profile:
            continue

        section = profile.get(day_type, {})
        probs = section.get("turn_on_probability", {})

        conf = float(probs.get(hour, 0.0))
        if conf < threshold:
            continue

        action = {
            "domain": domain,
            "action": "turn_on",
            "confidence": conf,
            "day_type": day_type,
        }

        if domain == "light":
            avg_b = section.get("avg_brightness", {})
            if hour in avg_b:
                action["brightness"] = avg_b[hour]

        actions.append(action)

    return {
        "room": room,
        "hour": hour,
        "day_type": day_type,
        "actions": actions,
    }

