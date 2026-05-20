from sqlalchemy import Column, DateTime, ForeignKey, String, Text, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.app.database import Base
from sqlalchemy.dialects.postgresql import JSONB


class FormType(Base):
    """SQLAlchemy model for Form Type definitions."""

    __tablename__ = "form_types"

    # Primary key
    form_type_id = Column(String(50), primary_key=True, index=True)

    # Basic fields
    form_name = Column(String(255), nullable=False, unique=True)
    description = Column(Text, nullable=True)

    # Versioning
    version = Column(String(20), nullable=False, default="1.0.0")
    schema_reference = Column(JSONB, nullable=True)

    # Timestamps
    created_by = Column(String(100))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    stages = relationship(
        "Stage",
        secondary="stage_form_types",
        back_populates="form_types"
    )
    permissions = relationship(
        "FormTypePermission", back_populates="form_type", cascade="all, delete-orphan"
    )
    records = relationship(
        "FormRecord", back_populates="form_type", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<FormType(id={self.form_type_id}, name={self.form_name})>"

    def to_dict(self):
        """Convert model to dictionary."""
        return {
            "form_type_id": self.form_type_id,
            "form_name": self.form_name,
            "description": self.description,
            "version": self.version,
            "schema_reference": self.schema_reference,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }
