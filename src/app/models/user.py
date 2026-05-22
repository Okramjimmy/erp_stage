"""SQLAlchemy model for Users."""

import uuid
from sqlalchemy import Boolean, Column, DateTime, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.app.database import Base


class User(Base):
    """SQLAlchemy model for application users."""

    __tablename__ = "users"

    # Primary key — UUID string
    user_id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))

    # Identity
    username = Column(String(100), nullable=False, unique=True, index=True)
    email = Column(String(255), nullable=False, unique=True, index=True)
    full_name = Column(String(255), nullable=False)

    # Profile fields
    department = Column(String(100), nullable=True)
    phone = Column(String(50), nullable=True)

    # Photo stored as a MinIO object key: "users/{user_id}_{department}/photo.{ext}"
    # Resolved to a presigned URL at display time via GET /api/v1/storage/url/{key}
    profile_photo_url = Column(Text, nullable=True)

    # Auth
    hashed_password = Column(Text, nullable=False)

    # Flags
    is_active = Column(Boolean, nullable=False, default=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    # One user → one UserRole row (role_ids stored as JSONB integer array)
    roles = relationship("UserRole", back_populates="user", cascade="all, delete-orphan", uselist=False)

    def __repr__(self):
        return f"<User(id={self.user_id}, username={self.username})>"

    def to_dict(self):
        """Convert model to dictionary (excludes hashed_password)."""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "full_name": self.full_name,
            "department": self.department,
            "phone": self.phone,
            "profile_photo_url": self.profile_photo_url,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
