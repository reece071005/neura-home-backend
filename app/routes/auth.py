from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app import models, schemas, auth
from app.database import get_db

router = APIRouter(prefix="/auth", tags=["authentication"])


@router.post("/register", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user: schemas.UserCreate, db: AsyncSession = Depends(get_db)):
    """Public registration.

    - If this is the very first user, they become admin.
    - After that, public registration is blocked (only admins can create users).
    """
    # Is this the first user in the system?
    result_any = await db.execute(select(models.User.id).limit(1))
    first_existing_user = result_any.scalar_one_or_none()
    is_first_user = first_existing_user is None

    if not is_first_user:
        # Only admins can create further users via the admin endpoint.
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Registration is closed. Ask an admin to create an account for you.",
        )

    # Password validation is handled by Pydantic schema validator

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

    # First user becomes admin by default
    role = models.UserRole.admin if is_first_user else models.UserRole.user

    hashed_password = auth.get_password_hash(user.password)
    db_user = models.User(
        email=user.email,
        username=user.username,
        hashed_password=hashed_password,
        role=role,
    )
    db.add(db_user)
    await db.commit()
    await db.refresh(db_user)
    return db_user



@router.post("/login", response_model=schemas.Token)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    """Login and get access token"""
    user = await auth.authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token_expires = timedelta(minutes=auth.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = auth.create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


