from sqlalchemy import Column, DateTime, ForeignKey, String
from sqlalchemy.sql import func

from src.app.database import Base


class StageFormType(Base):
    """SQLAlchemy association model for linking Stages to FormTypes."""

    __tablename__ = "stage_form_types"

    stage_id = Column(
        String(50), 
        ForeignKey("stages.stage_id", ondelete="CASCADE"), 
        primary_key=True
    )
    form_type_id = Column(
        String(50), 
        ForeignKey("form_types.form_type_id", ondelete="CASCADE"), 
        primary_key=True
    )

    linked_by = Column(String(100))
    linked_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<StageFormType(stage_id={self.stage_id}, form_type_id={self.form_type_id})>"
