from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class FormRecordCreate(BaseModel):
    stage_id: Optional[str] = None
    form_type_id: str
    data: Dict[str, Any] = Field(default_factory=dict)
    created_by: Optional[str] = None


class FormRecordUpdate(BaseModel):
    data: Dict[str, Any] = Field(default_factory=dict)


class FormRecordResponse(BaseModel):
    record_id: str
    form_type_id: str
    stage_id: Optional[str]
    docname: str
    status: str
    assigned_role: Optional[str] = None
    assigned_to: Optional[str] = None
    assigned_at: Optional[datetime] = None
    data: Optional[Dict[str, Any]] = None
    schema_snapshot: Optional[Dict[str, Any]] = None
    form_version: Optional[str] = None
    amended_from: Optional[str] = None
    parent_record_id: Optional[str] = None
    parent_form_type_id: Optional[str] = None
    parent_field_name: Optional[str] = None
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
