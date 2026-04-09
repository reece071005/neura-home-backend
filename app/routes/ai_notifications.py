from datetime import datetime
from typing import Literal, Optional, Any, Dict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models import AINotification
from app import auth, models


router = APIRouter(prefix="/ai-notifications", tags=["ai-notifications"])


class AINotificationCreate(BaseModel):
    message: str
    room: Optional[str] = None
    entity_id: Optional[str] = None
    notification_type: str = "executed"
    action_type: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None


class AINotificationResponse(BaseModel):
    id: int
    message: str
    room: Optional[str] = None
    entity_id: Optional[str] = None
    notification_type: str
    action_type: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None
    created_at: datetime
    is_read: bool
    read_at: Optional[datetime] = None


@router.get("/get-all-notifications")
async def get_all_ai_notifications(
    skip: int = 0,
    limit: int = 50,
    status: Literal["all", "read", "unread"] = "all",
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    stmt = select(AINotification).order_by(AINotification.created_at.desc())

    if status == "unread":
        stmt = stmt.where(AINotification.is_read.is_(False))
    elif status == "read":
        stmt = stmt.where(AINotification.is_read.is_(True))

    stmt = stmt.offset(skip).limit(limit)

    result = await db.execute(stmt)
    notifications = result.scalars().all()

    return [
        AINotificationResponse(
            id=n.id,
            message=n.message,
            room=n.room,
            entity_id=n.entity_id,
            notification_type=n.notification_type,
            action_type=n.action_type,
            meta=n.meta,
            created_at=n.created_at,
            is_read=n.is_read,
            read_at=n.read_at,
        )
        for n in notifications
    ]


@router.get("/get-notification/{notification_id}")
async def get_ai_notification_by_id(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    result = await db.execute(
        select(AINotification).where(AINotification.id == notification_id)
    )
    notification = result.scalar_one_or_none()

    if notification is None:
        raise HTTPException(status_code=404, detail="AI notification not found")

    if not notification.is_read:
        notification.is_read = True
        notification.read_at = datetime.utcnow()
        db.add(notification)
        await db.commit()
        await db.refresh(notification)

    return AINotificationResponse(
        id=notification.id,
        message=notification.message,
        room=notification.room,
        entity_id=notification.entity_id,
        notification_type=notification.notification_type,
        action_type=notification.action_type,
        meta=notification.meta,
        created_at=notification.created_at,
        is_read=notification.is_read,
        read_at=notification.read_at,
    )


@router.post("/notification", include_in_schema=False)
async def create_ai_notification(
    body: AINotificationCreate,
    db: AsyncSession = Depends(get_db),
):
    entry = AINotification(
        message=body.message,
        room=body.room,
        entity_id=body.entity_id,
        notification_type=body.notification_type,
        action_type=body.action_type,
        meta=body.meta,
        is_read=False,
        read_at=None,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)

    return {
        "id": entry.id,
        "message": entry.message,
        "created_at": entry.created_at,
    }