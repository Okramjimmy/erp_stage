"""SQLAlchemy model for Departments."""

import uuid
from sqlalchemy import Column, DateTime, String, Text
from sqlalchemy.sql import func
from src.app.database import Base


class Department(Base):
    """SQLAlchemy model for departments."""

    __tablename__ = "departments"

    department_id = Column(String(36), primary_key=True, index=True, default=lambda: str(uuid.uuid4()))
    name = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self):
        return f"<Department(id={self.department_id}, name={self.name})>"

    def to_dict(self):
        """Convert model to dictionary."""
        return {
            "department_id": self.department_id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
