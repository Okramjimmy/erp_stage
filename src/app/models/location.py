"""SQLAlchemy model for Locations."""

import uuid
from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.sql import func
from src.app.database import Base


class Location(Base):
    """SQLAlchemy model for locations."""

    __tablename__ = "locations"

    location_id = Column(
        String(36),
        primary_key=True,
        index=True,
        default=lambda: str(uuid.uuid4()),
    )
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self):
        return f"<Location(id={self.location_id}, name={self.name})>"

    def to_dict(self):
        """Convert model to dictionary."""
        return {
            "location_id": self.location_id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
