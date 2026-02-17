"""
API for vision service to create detection notifications and get all notifications.
"""
import base64
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import NOTIFY_DIR
from app.database import get_db
from app.models import DetectionNotification
from app import auth, models

router = APIRouter(prefix="/vision", tags=["vision"])


class DetectionNotificationCreate(BaseModel):
    message: str
    camera_entity: str
    image_path: str | None = None


class DetectionNotificationResponse(BaseModel):
    id: int
    message: str
    camera_entity: str
    image: str | None = None  # base64-encoded JPEG
    created_at: datetime


def _image_path_to_base64(image_path: str | None) -> str | None:
    if not image_path:
        return None
    path = Path(NOTIFY_DIR) / image_path
    print(path)
    if not path.exists():
        return None
    try:
        data = path.read_bytes()
        # Return a JPEG data URL (data:image/jpeg;base64,...) for easy use in <img src="...">
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"
    except Exception:
        return None


@router.get("/get-all-notifications")
async def get_all_notifications(
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """
    Return a paginated list of detection notifications, newest first.

    - skip: number of items to skip (for pagination)
    - limit: maximum number of items to return
    """
    stmt = (
        select(DetectionNotification)
        .order_by(DetectionNotification.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    result = await db.execute(stmt)
    notifications = result.scalars().all()
    return [
        DetectionNotificationResponse(
            id=n.id,
            message=n.message,
            camera_entity=n.camera_entity,
            image=_image_path_to_base64(n.image_path),
            created_at=n.created_at,
        )
        for n in notifications
    ]


@router.get(
    "/get-notification/{notification_id}",
)
async def get_notification_by_id(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    result = await db.execute(select(DetectionNotification).where(DetectionNotification.id == notification_id))
    notification = result.scalar_one_or_none()
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")

    print(notification.image_path)
    return DetectionNotificationResponse(
        id=notification.id,
        message=notification.message,
        camera_entity=notification.camera_entity,
        image=_image_path_to_base64(notification.image_path),
        created_at=notification.created_at,
    )

@router.post(
    "/notification",
    include_in_schema=False
)
async def create_detection_notification(
    body: DetectionNotificationCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a detection notification (called by vision container when something is detected)."""
    entry = DetectionNotification(
        message=body.message,
        camera_entity=body.camera_entity,
        image_path=body.image_path,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return {"id": entry.id, "message": entry.message, "created_at": entry.created_at}
