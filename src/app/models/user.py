"""SQLAlchemy model for Users."""

import uuid
from typing import Optional
from sqlalchemy import Boolean, Column, DateTime, String, Text, ForeignKey
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

    # Assignments
    manager_id = Column(String(36), ForeignKey("users.user_id"), nullable=True)

    # Profile fields
    dept = Column(String(36), ForeignKey("departments.department_id"), nullable=True)
    location_id = Column(String(36), ForeignKey("locations.location_id"), nullable=True)
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
    department_rel = relationship("Department", foreign_keys=[dept], lazy="selectin")
    location_rel = relationship("Location", foreign_keys=[location_id], lazy="selectin")

    @property
    def department(self) -> Optional[str]:
        return self.department_rel.name if self.department_rel else None

    @property
    def location(self) -> Optional[str]:
        return self.location_rel.name if self.location_rel else None

    def __repr__(self):
        return f"<User(id={self.user_id}, username={self.username})>"

    def to_dict(self):
        """Convert model to dictionary (excludes hashed_password)."""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "full_name": self.full_name,
            "dept": self.dept,
            "department": self.department,
            "location_id": self.location_id,
            "location": self.location,
            "phone": self.phone,
            "profile_photo_url": self.profile_photo_url,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

