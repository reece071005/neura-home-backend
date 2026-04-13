"""
API for vision service to create detection notifications and get all notifications.
"""
import base64
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import NOTIFY_DIR
from app.database import get_db
from app.models import DetectionNotification
from app import auth, models, schemas

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
    is_read: bool
    read_at: datetime | None = None


def _image_path_to_base64(image_path: str | None) -> str | None:
    if not image_path:
        return None
    path = Path(NOTIFY_DIR) / image_path
    print(path)
    if not path.exists():
        return None
    try:
        data = path.read_bytes()
        # tjis will return a JPEG data URL (data:image/jpeg;base64,...) for easy use in <img src="...">
        b64 = base64.b64encode(data).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"
    except Exception:
        return None


@router.get("/get-all-notifications")
async def get_all_notifications(
    skip: int = 0,
    limit: int = 50,
    status: Literal["all", "read", "unread"] = "all",
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """
    Return a paginated list of detection notifications, newest first.

    - skip: number of items to skip (for pagination)
    - limit: maximum number of items to return
    """
    stmt = select(DetectionNotification).order_by(
        DetectionNotification.created_at.desc()
    )
    if status == "unread":
        stmt = stmt.where(DetectionNotification.is_read.is_(False))
    elif status == "read":
        stmt = stmt.where(DetectionNotification.is_read.is_(True))
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    notifications = result.scalars().all()
    return [
        DetectionNotificationResponse(
            id=n.id,
            message=n.message,
            camera_entity=n.camera_entity,
            image=_image_path_to_base64(n.image_path),
            created_at=n.created_at,
            is_read=n.is_read,
            read_at=n.read_at,
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
    result = await db.execute(
        select(DetectionNotification).where(
            DetectionNotification.id == notification_id
        )
    )
    notification = result.scalar_one_or_none()
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")

    # Mark notification as read when it is fetched by ID
    if not notification.is_read:
        notification.is_read = True
        notification.read_at = datetime.utcnow()
        db.add(notification)
        await db.commit()
        await db.refresh(notification)

    return DetectionNotificationResponse(
        id=notification.id,
        message=notification.message,
        camera_entity=notification.camera_entity,
        image=_image_path_to_base64(notification.image_path),
        created_at=notification.created_at,
        is_read=notification.is_read,
        read_at=notification.read_at,
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
        is_read=False,
        read_at=None,
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return {"id": entry.id, "message": entry.message, "created_at": entry.created_at}


##camera tracking endpoints
@router.get("/cameras", response_model=schemas.CameraResponse)
async def get_tracked_cameras(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """
    Retrieve all tracked camera entity IDs.
    Returns an empty list if no cameras are configured.
    """
    result = await db.execute(
        select(models.Configuration).where(models.Configuration.key == "tracked_cameras")
    )
    config = result.scalar_one_or_none()

    if not config or not config.value or "entity_ids" not in config.value:
        return schemas.CameraResponse(entity_ids=[])

    return schemas.CameraResponse(entity_ids=config.value["entity_ids"])


@router.post("/cameras")
async def add_camera(
    payload: schemas.CameraAdd,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """
    Add a single camera entity ID to the tracked cameras list.
    If the camera is already tracked, returns success without duplicates.
    """
    result = await db.execute(
        select(models.Configuration).where(models.Configuration.key == "tracked_cameras")
    )
    config = result.scalar_one_or_none()

    if config:
        entity_ids = list(config.value.get("entity_ids", []))
        if payload.entity_id not in entity_ids:
            entity_ids.append(payload.entity_id)
            config.value = {"entity_ids": entity_ids}
    else:
        config = models.Configuration(
            key="tracked_cameras",
            value={"entity_ids": [payload.entity_id]}
        )
        db.add(config)

    await db.commit()
    await db.refresh(config)

    return {
        "message": f"Camera {payload.entity_id} added successfully",
        "entity_ids": config.value["entity_ids"]
    }


@router.post("/cameras/batch")
async def add_cameras_batch(
    payload: schemas.CameraBatchAdd,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """
    Add multiple camera entity IDs to the tracked cameras list (batch operation).
    Duplicates are automatically filtered out.
    """
    if not payload.entity_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="entity_ids list cannot be empty"
        )

    result = await db.execute(
        select(models.Configuration).where(models.Configuration.key == "tracked_cameras")
    )
    config = result.scalar_one_or_none()

    if config:
        existing_ids = set(config.value.get("entity_ids", []))
        new_ids = [eid for eid in payload.entity_ids if eid not in existing_ids]
        if not new_ids:
            return {
                "message": "All cameras are already tracked",
                "entity_ids": list(existing_ids),
                "added_count": 0
            }
        entity_ids = list(existing_ids) + new_ids
        config.value = {"entity_ids": entity_ids}
        added_count = len(new_ids)
    else:
        # remove duplicates from input
        entity_ids = list(dict.fromkeys(payload.entity_ids))  # Preserves order while removing duplicates
        config = models.Configuration(
            key="tracked_cameras",
            value={"entity_ids": entity_ids}
        )
        db.add(config)
        added_count = len(entity_ids)

    await db.commit()
    await db.refresh(config)

    return {
        "message": f"Added {added_count} camera(s) successfully",
        "entity_ids": config.value["entity_ids"],
        "added_count": added_count
    }


@router.delete("/cameras/{entity_id}")
async def delete_camera(
    entity_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """
    Remove a camera entity ID from the tracked cameras list.
    Returns 404 if the camera is not found in the tracked list.
    """
    result = await db.execute(
        select(models.Configuration).where(models.Configuration.key == "tracked_cameras")
    )
    config = result.scalar_one_or_none()

    if not config or not config.value or "entity_ids" not in config.value:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera {entity_id} not found in tracked cameras"
        )

    entity_ids = list(config.value["entity_ids"])
    if entity_id not in entity_ids:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Camera {entity_id} not found in tracked cameras"
        )

    entity_ids.remove(entity_id)
    config.value = {"entity_ids": entity_ids}

    await db.commit()
    await db.refresh(config)

    return {
        "message": f"Camera {entity_id} removed successfully",
        "entity_ids": config.value["entity_ids"]
    }
