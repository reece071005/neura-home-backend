from datetime import datetime, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app import auth, models, schemas
from app.database import get_db

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.post(
    "/expo-token",
    response_model=schemas.PushNotificationTokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upsert_expo_push_token(
    payload: schemas.ExpoPushTokenUpsert,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """Create or update the current user's Expo push token."""
    now = datetime.now(timezone.utc)

    existing = None
    if payload.device_id:
        result = await db.execute(
            select(models.PushNotificationToken).where(
                models.PushNotificationToken.user_id == current_user.id,
                models.PushNotificationToken.device_id == payload.device_id,
            )
        )
        existing = result.scalar_one_or_none()

    if existing is None:
        result = await db.execute(
            select(models.PushNotificationToken).where(
                models.PushNotificationToken.expo_push_token == payload.expo_push_token
            )
        )
        existing = result.scalar_one_or_none()

    if existing:
        existing.user_id = current_user.id
        existing.expo_push_token = payload.expo_push_token
        existing.device_id = payload.device_id
        existing.platform = payload.platform
        existing.is_active = True
        existing.last_seen_at = now
        await db.commit()
        await db.refresh(existing)
        return existing

    token = models.PushNotificationToken(
        user_id=current_user.id,
        expo_push_token=payload.expo_push_token,
        device_id=payload.device_id,
        platform=payload.platform,
        is_active=True,
        last_seen_at=now,
    )
    db.add(token)
    await db.commit()
    await db.refresh(token)
    return token
