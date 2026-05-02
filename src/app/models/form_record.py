from sqlalchemy import Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

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
    docname = Column(String(255), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="Draft")
    data = Column(Text, nullable=True)
    amended_from = Column(
        String(50), ForeignKey("form_records.record_id"), nullable=True
    )
    submitted_by = Column(String(100), nullable=True)
    submitted_at = Column(DateTime(timezone=True), nullable=True)
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    form_type = relationship("FormType", back_populates="records")
    amended_record = relationship("FormRecord", remote_side="FormRecord.record_id")
