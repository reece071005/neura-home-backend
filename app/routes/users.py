from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete
from app import models, schemas, auth
from app.database import get_db
from pathlib import Path
from app.routes import userfaces as userfaces_routes

router = APIRouter(prefix="/auth/users", tags=["users"])



@router.get("/get-users", response_model=list[schemas.UserResponse])
async def get_users(
    db: AsyncSession = Depends(get_db),
    current_admin: models.User = Depends(auth.get_current_admin_user),
):
    """Admin-only endpoint to get all users."""
    result = await db.execute(select(models.User))
    return result.scalars().all()

@router.post("/add-users", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user_as_admin(
    user: schemas.AdminCreateUser,
    db: AsyncSession = Depends(get_db),
    current_admin: models.User = Depends(auth.get_current_admin_user),
):
    """Admin-only endpoint to create new users with explicit roles."""
    # Check if user already exists (by email)
    result_email = await db.execute(
        select(models.User).where(models.User.email == user.email)
    )
    db_user_email = result_email.scalar_one_or_none()
    if db_user_email:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered",
        )

    # Check if username is taken
    result_username = await db.execute(
        select(models.User).where(models.User.username == user.username)
    )
    db_user_username = result_username.scalar_one_or_none()
    if db_user_username:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already taken",
        )

    hashed_password = auth.get_password_hash(user.password)
    db_user = models.User(
        email=user.email,
        username=user.username,
        hashed_password=hashed_password,
        role=user.role,
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user

@router.put("/change-role", response_model=schemas.UserResponse)
async def change_user_role(
    user: schemas.ChangeUserRole,
    db: AsyncSession = Depends(get_db),
    current_admin: models.User = Depends(auth.get_current_admin_user),
):
    """Admin-only endpoint to change a user's role."""
    result = await db.execute(
        select(models.User).where(models.User.username == user.username)
    )
    db_user = result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    db_user.role = user.role
    await db.commit()
    await db.refresh(db_user)
    return db_user

@router.put("/change-password", response_model=schemas.UserResponse)
async def change_user_password(
    user: schemas.ChangeUserPassword,
    db: AsyncSession = Depends(get_db),
    current_admin: models.User = Depends(auth.get_current_admin_user),
):
    """Admin-only endpoint to change a user's role."""
    result = await db.execute(
        select(models.User).where(models.User.username == user.username)
    )
    db_user = result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    db_user.hashed_password = auth.get_password_hash(user.password)
    await db.commit()
    await db.refresh(db_user)
    return db_user

@router.put("/change-email", response_model=schemas.UserResponse)
async def change_user_email(
    user: schemas.ChangeUserEmail,
    db: AsyncSession = Depends(get_db),
    current_admin: models.User = Depends(auth.get_current_admin_user),
):
    """Admin-only endpoint to change a user's email."""
    result = await db.execute(
        select(models.User).where(models.User.username == user.username)
    )
    db_user = result.scalar_one_or_none()
    if not db_user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    db_user.email = user.email
    await db.commit()
    await db.refresh(db_user)
    return db_user

@router.delete("/delete-user/{user_id}", status_code=status.HTTP_200_OK)
async def delete_user_as_admin(
        user_id: int,
        db: AsyncSession = Depends(get_db),
        current_admin: models.User = Depends(auth.get_current_admin_user),
):
    """Admin-only endpoint to delete a user by id."""
    result = await db.execute(select(models.User).where(models.User.id == user_id))
    db_user = result.scalar_one_or_none()

    if not db_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    if db_user.role == "admin":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete admin users",
        )

    # Delete related user state rows first to satisfy FK constraints
    await db.execute(
        delete(models.UserState).where(models.UserState.user_id == user_id)
    )

    # Delete related userface image (if any) from disk
    username = db_user.username
    project_root = Path(__file__).resolve().parents[2]
    residents_dir = project_root / "residents"
    residents_dir.mkdir(parents=True, exist_ok=True)
    for ext in [".jpg", ".jpeg", ".png", ".webp"]:
        p = residents_dir / f"{username}{ext}"
        try:
            if p.exists():
                p.unlink()
        except OSError:
            continue

    await db.delete(db_user)
    await db.commit()
    return {"message": "User deleted successfully"}


@router.get("/get-user-state", response_model=schemas.UserStateResponse)
async def get_user_state(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Get the current state of a user for dashboard. If no state exists, returns an empty dictionary."""
    try:
        result = await db.execute(select(models.UserState).where(models.UserState.user_id == current_user.id))
        return result.scalar_one_or_none()
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User state not found")
        return None

@router.post("/set-user-state", response_model=schemas.UserStateResponse)
async def set_user_state(
    state: schemas.UserState,
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):

    """Set the state of a user. Creates a new state row if none exists for this user for dashboard."""
    result = await db.execute(select(models.UserState).where(models.UserState.user_id == current_user.id))
    db_user_state = result.scalar_one_or_none()

    if db_user_state:
        await db.execute(
            update(models.UserState).where(models.UserState.user_id == current_user.id).values(state=state.state)
        )
        await db.commit()
        await db.refresh(db_user_state)
        return db_user_state
    else:
        db_user_state = models.UserState(user_id=current_user.id, state=state.state)
        db.add(db_user_state)
        await db.commit()
        await db.refresh(db_user_state)
        return db_user_state


@router.get("/get-user-profile", response_model=schemas.UserResponse)
async def get_user_profile(
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
):
    """Get the profile of the current user."""
    return current_user