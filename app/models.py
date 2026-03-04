from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, JSON, UniqueConstraint
from sqlalchemy.types import Enum as SqlEnum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base
import enum


class UserRole(enum.Enum):
    admin = "admin"
    user = "user"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    role = Column(SqlEnum(UserRole, name="user_role"), nullable=False, default=UserRole.user)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class UserState(Base):
    __tablename__ = "user_states"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    state = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Userface(Base):
    __tablename__ = "userfaces"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    image_path = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class DetectionNotification(Base):
    """Vision detection events (e.g. resident/stranger at front door)."""
    __tablename__ = "detection_notifications"

    id = Column(Integer, primary_key=True, index=True)
    message = Column(String, nullable=False)
    camera_entity = Column(String, nullable=False, index=True)
    image_path = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    is_read = Column(Boolean, nullable=False, default=False)
    read_at = Column(DateTime(timezone=True), nullable=True)

class Configuration(Base):
    __tablename__ = "configurations"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String, nullable=False, index=True)
    value = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class Room(Base):
    """User-defined room with a unique name and list of device entity IDs.
    Each entity_id can belong to at most one room per user (enforced in API).
    """
    __tablename__ = "rooms"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_room_user_name"),)

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String, nullable=False)
    entity_ids = Column(JSON, nullable=False, default=list)  # list of entity_id strings
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

    user = relationship("User", backref="rooms")

    @property
    def username(self) -> str | None:
        """Username of the user who owns this room (when user is loaded)."""
        return self.user.username if self.user else None