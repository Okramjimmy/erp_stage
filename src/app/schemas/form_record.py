from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class FormRecordCreate(BaseModel):
    form_type_id: str
    data: Dict[str, Any] = Field(default_factory=dict)
    created_by: Optional[str] = None


class FormRecordUpdate(BaseModel):
    data: Dict[str, Any] = Field(default_factory=dict)


class FormRecordResponse(BaseModel):
    record_id: str
    form_type_id: str
    docname: str
    status: str
    assigned_role: Optional[str] = None
    assigned_department: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    amended_from: Optional[str] = None
    submitted_by: Optional[str] = None
    submitted_at: Optional[datetime] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FormRecordList(BaseModel):
    items: List[FormRecordResponse]
    total: int
