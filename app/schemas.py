from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional
from datetime import datetime
from app.models import UserRole


class UserBase(BaseModel):
    email: EmailStr
    username: str


class UserCreate(UserBase):
    """Public registration payload (no role; role is decided by server)."""

    password: str

    @field_validator("password")
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v


class AdminCreateUser(UserBase):
    """Admin-only payload to create users with explicit roles."""

    password: str
    role: UserRole

    @field_validator("password")
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v

# Admin-only endpoint to change a users' data

class ChangeUserEmail(BaseModel):
    username: str
    email: EmailStr

class ChangeUserRole(BaseModel):
    username: str
    role: UserRole


class ChangeUserPassword(BaseModel):
    username: str
    password: str

    @field_validator("password")
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v

# Response schemas
class UserResponse(UserBase):
    id: int
    is_active: bool
    created_at: datetime
    role: UserRole

    class Config:
        from_attributes = True


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: Optional[str] = None

# Home Assistant schemas
class LightState(BaseModel):
    entity_id: str
    brightness: int

class LightStateResponse(BaseModel):
    message: str
    success: bool