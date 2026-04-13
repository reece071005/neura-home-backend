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
    """List all rooms."""
    result = await db.execute(
        select(models.Room)
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
    """Get a room by id."""
    result = await db.execute(
        select(models.Room)
        .where(models.Room.id == room_id)
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
    Create a room. Name must be unique for the owner.
    No entity_id may already belong to another room for the owner.
    The owner of the room is determined by payload.user_id (if provided) or defaults to the current user.
    """
    # Determine the owner of the room: explicit user_id or current user
    owner_user_id = payload.user_id or current_user.id

    owner_result = await db.execute(
        select(models.User).where(models.User.id == owner_user_id)
    )
    owner_user = owner_result.scalar_one_or_none()
    if not owner_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User with id {owner_user_id} does not exist",
        )

    # Unique name per owner
    result_name = await db.execute(
        select(models.Room).where(
            models.Room.user_id == owner_user_id,
            models.Room.name == payload.name,
        )
    )
    if result_name.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Room with name '{payload.name}' already exists",
        )

    # Entity uniqueness: no entity may be in any other room for this owner
    result_rooms = await db.execute(
        select(models.Room).where(models.Room.user_id == owner_user_id)
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
        user_id=owner_user_id,
        name=payload.name,
        entity_ids=new_entity_ids,
    )
    db.add(room)
    await db.commit()
    await db.refresh(room)
    room.user = owner_user  # for RoomResponse.username
    return room


@router.patch("/{room_id}", response_model=schemas.RoomResponse)
async def update_room(
    room_id: int,
    payload: schemas.RoomUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """
    Update a room. Name must remain unique for the room owner.
    Updated entity_ids must not include any entity already in another room for the same owner (excluding this one).
    The room owner can also be changed by providing payload.user_id.
    """
    result = await db.execute(
        select(models.Room).where(models.Room.id == room_id)
    )
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")

    # Determine the (potentially new) owner of the room
    new_user_id = payload.user_id if payload.user_id is not None else room.user_id

    owner_result = await db.execute(
        select(models.User).where(models.User.id == new_user_id)
    )
    owner_user = owner_result.scalar_one_or_none()
    if not owner_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User with id {new_user_id} does not exist",
        )

    # Name uniqueness for the new owner
    new_name = payload.name if payload.name is not None else room.name
    result_name = await db.execute(
        select(models.Room).where(
            models.Room.user_id == new_user_id,
            models.Room.name == new_name,
            models.Room.id != room_id,
        )
    )
    if result_name.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Room with name '{new_name}' already exists",
        )

    # Entity uniqueness for the new owner
    effective_entity_ids = (
        list(dict.fromkeys(payload.entity_ids))
        if payload.entity_ids is not None
        else (room.entity_ids or [])
    )
    result_rooms = await db.execute(
        select(models.Room).where(models.Room.user_id == new_user_id)
    )
    other_rooms = result_rooms.scalars().all()
    used_entities = _entity_ids_in_other_rooms(other_rooms, exclude_room_id=room_id)
    conflicting = [e for e in effective_entity_ids if e in used_entities]
    if conflicting:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Entity IDs already in another room: {conflicting}",
        )

    # Apply changes
    room.user_id = new_user_id
    room.name = new_name
    room.entity_ids = effective_entity_ids

    await db.commit()
    await db.refresh(room)
    room.user = owner_user  # for RoomResponse.username
    return room


@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_room(
    room_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_active_user),
):
    """Delete a room."""
    result = await db.execute(
        select(models.Room).where(models.Room.id == room_id)
   )
    room = result.scalar_one_or_none()
    if not room:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Room not found")
    await db.delete(room)
    await db.commit()


@router.get("/internal/all")
async def list_all_rooms_internal(
    db: AsyncSession = Depends(get_db),
):
   
    result = await db.execute(select(models.Room))
    rooms = result.scalars().all()

    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "name": r.name,
            "entity_ids": r.entity_ids,
        }
        for r in rooms
    ]