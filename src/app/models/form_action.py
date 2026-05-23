from sqlalchemy import Column, DateTime, ForeignKey, String, Text, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.app.database import Base


class FormAction(Base):
    __tablename__ = "form_actions"

    action_id = Column(Integer, primary_key=True, autoincrement=True)
    record_id = Column(String(50), ForeignKey("form_records.record_id", ondelete="CASCADE"), nullable=False, index=True)
    from_state = Column(String(100), nullable=False)
    to_state = Column(String(100), nullable=False)
    action_type = Column(String(50), nullable=False)
    performed_by = Column(String(50), ForeignKey("users.user_id"), nullable=False)
    remarks = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    record = relationship("FormRecord", back_populates="actions")