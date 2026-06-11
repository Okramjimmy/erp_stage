"""SQLAlchemy model for Workflow Assignments.

Maps (stage, form_type, role) → user, enabling explicit assignment chains
like Worker → Manager → Reviewer instead of ambiguous role+department matching.
"""

import uuid

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.app.database import Base


class WorkflowAssignment(Base):
    """Assigns a specific user to a role for a given stage + form type combination."""

    __tablename__ = "workflow_assignments"

    assignment_id = Column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )

    stage_id = Column(
        String(50),
        ForeignKey("stages.stage_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    form_type_id = Column(
        String(50),
        ForeignKey("form_types.form_type_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    role = Column(String(50), nullable=False)

    user_id = Column(
        String(50),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    assigned_by = Column(
        String(50),
        ForeignKey("users.user_id"),
        nullable=True,
    )

    active = Column(Boolean, default=True, nullable=False)

    created_at = Column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relationships
    stage = relationship("Stage", foreign_keys=[stage_id])
    form_type = relationship("FormType", foreign_keys=[form_type_id])
    user = relationship("User", foreign_keys=[user_id])

    def __repr__(self):
        return (
            f"<WorkflowAssignment("
            f"stage={self.stage_id}, form_type={self.form_type_id}, "
            f"role={self.role}, user={self.user_id})>"
        )
