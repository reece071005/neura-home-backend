from pydantic import BaseModel, EmailStr, field_validator
from typing import Optional, Literal
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


class ChangeOwnPassword(BaseModel):
    old_password: str
    new_password: str
    confirm_password: str

    @field_validator("new_password")
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

class UserState(BaseModel):
    state: dict

class UserStateResponse(BaseModel):
    id: int
    user_id: int
    state: dict
    created_at: datetime
    updated_at: Optional[datetime] = None 


# Home Assistant schemas
class LightState(BaseModel):
    entity_id: str
    state: Literal["on", "off"]
    brightness: Optional[int] = None

class LightStateResponse(BaseModel):
    message: str
    success: bool

class CoverState(BaseModel):
    entity_id: str
    position: int
class CoverStateResponse(BaseModel):
    message: str
    success: bool


class FanState(BaseModel):
    entity_id: str
    # Optional fields mirror common fan services; all optional so caller can choose.
    state: Literal["on", "off"]
    percentage: Optional[int] = None
    oscillating: Optional[bool] = None
    direction: Optional[str] = None  # "forward" / "reverse"


class FanStateResponse(BaseModel):
    message: str
    success: bool


class ClimateState(BaseModel):
    entity_id: str
    state: Literal["on", "off"]
    temperature: Optional[float] = None
    hvac_mode: Optional[str] = None
    preset_mode: Optional[str] = None
    fan_mode: Optional[str] = None
    swing_mode: Optional[str] = None
    swing_horizontal_mode: Optional[str] = None

class ClimateStateResponse(BaseModel):
    message: str
    success: bool

class DeviceInfo(BaseModel):
    entity_id: str
    kind: str
    name: str


class DeviceControlRequest(BaseModel):
    entity_id: str
    domain: Literal["light", "fan", "cover", "climate"]
    state: Literal["on", "off"]
    brightness: Optional[int] = None
    temperature: Optional[float] = None
    hvac_mode: Optional[str] = None
    position: Optional[int] = None


class HomeAssistantInstance(BaseModel):
    name: str
    ip: str
    port: int
    base_url: str


class HomeAssistantUrl(BaseModel):
    url: str


class HomeAssistantSecret(BaseModel):
    secret: str


class HomeAssistantSecretResponse(BaseModel):
    secret: str


class HomeAssistantConfig(BaseModel):
    """Combined payload for Home Assistant URL and optional secret."""
    url: str
    secret: Optional[str] = None


class HomeAssistantConfigResponse(BaseModel):
    """Combined response: URL and decrypted secret (if configured)."""
    url: str
    secret: Optional[str] = None


# ---------- Userfaces ----------

class UserfaceResponse(BaseModel):
    user_id: int
    username: str
    name: str
    image_base64: str

class UserfaceCreate(BaseModel):
    username: str
    name: str
    status: str

class UserfaceDelete(BaseModel):
    username: str
    name: str
    status: str


# ---------- Camera Tracking ----------

class CameraAdd(BaseModel):
    entity_id: str


class CameraBatchAdd(BaseModel):
    entity_ids: list[str]


class CameraResponse(BaseModel):
    entity_ids: list[str]


class CameraDelete(BaseModel):
    entity_id: str


# ---------- Room configurations ----------

class RoomBase(BaseModel):
    name: str
    entity_ids: list[str] = []


class RoomCreate(RoomBase):
    pass


class RoomUpdate(BaseModel):
    name: Optional[str] = None
    entity_ids: Optional[list[str]] = None


class RoomResponse(BaseModel):
    id: int
    user_id: int
    username: str
    name: str
    entity_ids: list[str]
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True