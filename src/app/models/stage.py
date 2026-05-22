from sqlalchemy import (
    ARRAY,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.app.database import Base


class Stage(Base):
    """SQLAlchemy model for Stage hierarchy."""

    __tablename__ = "stages"

    # Primary key
    stage_id = Column(String(50), primary_key=True, index=True)

    # Basic fields
    stage_name = Column(String(255), nullable=False)
    parent_stage_id = Column(String(50), ForeignKey("stages.stage_id"), nullable=True)

    # Hierarchical fields
    stage_path = Column(Text, nullable=False, unique=True)
    depth_level = Column(Integer, nullable=False, default=0)
    lineage_path = Column(ARRAY(String), nullable=False)

    # Counts
    children_count = Column(Integer, nullable=False, default=0)
    formtype_count = Column(Integer, nullable=False, default=0)

    # Visibility
    is_root = Column(Boolean, nullable=False, default=False)
    is_leaf = Column(Boolean, nullable=False, default=True)
    visibility_scope = Column(String(20), default="private")
    wbs_prefix = Column(String(10), nullable=True)

    # Timestamps
    created_by = Column(String(100))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Metadata
    metadata_reference = Column(Text)

    # Relationships
    parent = relationship("Stage", remote_side=[stage_id], backref="children")
    form_types = relationship(
        "FormType",
        secondary="stage_form_types",
        back_populates="stages"
    )
    permissions = relationship(
        "StagePermission", back_populates="stage", cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<Stage(id={self.stage_id}, name={self.stage_name}, path={self.stage_path})>"

    def to_dict(self):
        """Convert model to dictionary."""
        return {
            "stage_id": self.stage_id,
            "stage_name": self.stage_name,
            "parent_stage_id": self.parent_stage_id,
            "stage_path": self.stage_path,
            "depth_level": self.depth_level,
            "lineage_path": self.lineage_path,
            "children_count": self.children_count,
            "formtype_count": self.formtype_count,
            "is_root": self.is_root,
            "is_leaf": self.is_leaf,
            "visibility_scope": self.visibility_scope,
            "wbs_prefix": self.wbs_prefix,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "metadata_reference": self.metadata_reference,
        }
