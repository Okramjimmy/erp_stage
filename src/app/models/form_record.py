from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB

from src.app.database import Base


class FormRecord(Base):
    __tablename__ = "form_records"

    record_id = Column(String(50), primary_key=True, index=True)
    form_type_id = Column(
        String(50),
        ForeignKey("form_types.form_type_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    stage_id = Column(String(50), nullable=True)
    docname = Column(String(255), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="Draft")
    assigned_role = Column(String(50), nullable=True)
    assigned_to = Column(String(50), ForeignKey("users.user_id"), nullable=True, index=True)
    assigned_at = Column(DateTime(timezone=True), nullable=True)

    data = Column(JSONB, nullable=True)
    schema_snapshot = Column(JSONB, nullable=True)
    form_version = Column(String(10), nullable=False)
    amended_from = Column(
        String(50), ForeignKey("form_records.record_id"), nullable=True
    )
    
    # Parent-Child Relationships
    parent_record_id = Column(
        String(50), ForeignKey("form_records.record_id", ondelete="CASCADE"), nullable=True
    )
    parent_form_type_id = Column(
        String(50), ForeignKey("form_types.form_type_id", ondelete="CASCADE"), nullable=True
    )
    parent_field_name = Column(String(100), nullable=True)
    
    submitted_by = Column(String(100), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    form_type = relationship("FormType", back_populates="records", foreign_keys=[form_type_id])
    amended_record = relationship("FormRecord", remote_side=[record_id], foreign_keys=[amended_from])
    parent_record = relationship(
        "FormRecord",
        remote_side=[record_id],
        foreign_keys=[parent_record_id],
        back_populates="child_records",
    )
    child_records = relationship(
        "FormRecord",
        back_populates="parent_record",
        cascade="all, delete-orphan",
        foreign_keys=[parent_record_id],
    )
    actions = relationship(
        "FormAction",
        back_populates="record",
        cascade="all, delete-orphan",
    )
    
    def __repr__(self):
        return f"<FormRecord(id={self.record_id}, docname={self.docname})>"