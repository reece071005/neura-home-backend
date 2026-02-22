from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app import models, schemas, auth
from app.database import get_db

router = APIRouter(prefix="/rooms", tags=["rooms"])


def _entity_ids_in_other_rooms(
    rooms: list[models.Room], exclude_room_id: int | None
) -> set[str]:
    """Return set of entity_ids that are already in some room (excluding room with exclude_room_id)."""
    used = set()
    for r in rooms:
        if exclude_room_id is not None and r.id == exclude_room_id:
            continue
        used.update(r.entity_ids or [])
    return used


@router.get("", response_model=list[schemas.RoomResponse])
async def list_rooms(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """List all rooms for the current user."""
    result = await db.execute(
        select(models.Room)
        .where(models.Room.user_id == current_user.id)
        .order_by(models.Room.name)
        .options(selectinload(models.Room.user))
    )
    rooms = result.scalars().all()
    return rooms


@router.get("/{room_id}", response_model=schemas.RoomResponse)
async def get_room(
    room_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """Get a room by id. Room must belong to the current user."""
    result = await db.execute(
        select(models.Room)
        .where(
            models.Room.id == room_id,
            models.Room.user_id == current_user.id,
        )
        .options(selectinload(models.Room.user))
    )
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    return room


@router.post("", response_model=schemas.RoomResponse, status_code=status.HTTP_201_CREATED)
async def create_room(
    payload: schemas.RoomCreate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """
    Create a room. Name must be unique for this user.
    No entity_id may already belong to another room for this user.
    Non-admin users can only have one room; admins can create multiple rooms.
    """
    # Non-admin users are limited to one room
    if current_user.role != models.UserRole.admin:
        result_existing = await db.execute(
            select(models.Room).where(models.Room.user_id == current_user.id).limit(1)
        )
        if result_existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Users can only have one room. Contact an admin to create additional rooms.",
            )

    # Unique name per user
    result_name = await db.execute(
        select(models.Room).where(
            models.Room.user_id == current_user.id,
            models.Room.name == payload.name,
        )
    )
    if result_name.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Room with name '{payload.name}' already exists",
        )

    # Entity uniqueness: no entity may be in any other room
    result_rooms = await db.execute(
        select(models.Room).where(models.Room.user_id == current_user.id)
    )
    other_rooms = result_rooms.scalars().all()
    used_entities = _entity_ids_in_other_rooms(other_rooms, exclude_room_id=None)
    new_entity_ids = list(dict.fromkeys(payload.entity_ids))  # dedupe preserving order
    conflicting = [e for e in new_entity_ids if e in used_entities]
    if conflicting:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Entity IDs already in another room: {conflicting}",
        )

    room = models.Room(
        user_id=current_user.id,
        name=payload.name,
        entity_ids=new_entity_ids,
    )
    db.add(room)
    await db.commit()
    await db.refresh(room)
    room.user = current_user  # for RoomResponse.username
    return room


@router.patch("/{room_id}", response_model=schemas.RoomResponse)
async def update_room(
    room_id: int,
    payload: schemas.RoomUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """
    Update a room. Name must remain unique for this user.
    Updated entity_ids must not include any entity already in another room (excluding this one).
    """
    result = await db.execute(
        select(models.Room).where(
            models.Room.id == room_id,
            models.Room.user_id == current_user.id,
        )
    )
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")

    if payload.name is not None:
        result_name = await db.execute(
            select(models.Room).where(
                models.Room.user_id == current_user.id,
                models.Room.name == payload.name,
                models.Room.id != room_id,
            )
        )
        if result_name.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Room with name '{payload.name}' already exists",
            )
        room.name = payload.name

    if payload.entity_ids is not None:
        result_rooms = await db.execute(
            select(models.Room).where(models.Room.user_id == current_user.id)
        )
        other_rooms = result_rooms.scalars().all()
        used_entities = _entity_ids_in_other_rooms(other_rooms, exclude_room_id=room_id)
        new_entity_ids = list(dict.fromkeys(payload.entity_ids))
        conflicting = [e for e in new_entity_ids if e in used_entities]
        if conflicting:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Entity IDs already in another room: {conflicting}",
            )
        room.entity_ids = new_entity_ids

    await db.commit()
    await db.refresh(room)
    room.user = current_user  # for RoomResponse.username
    return room


@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_room(
    room_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """Delete a room. Room must belong to the current user."""
    result = await db.execute(
        select(models.Room).where(
            models.Room.id == room_id,
            models.Room.user_id == current_user.id,
        )
    )
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    await db.delete(room)
    await db.commit()
