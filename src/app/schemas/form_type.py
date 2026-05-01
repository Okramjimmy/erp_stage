from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class FormTypeBase(BaseModel):
    """Base schema for Form Type."""

    form_name: str = Field(..., min_length=1, max_length=255)
    stage_id: str = Field(..., min_length=1)
    version: str = Field(default="1.0.0", pattern=r"^\d{1,3}\.\d{1,3}\.\d{1,3}$")


class FormTypeCreate(FormTypeBase):
    """Schema for creating a Form Type."""

    schema: Optional[Dict[str, Any]] = None


class FormTypeUpdate(BaseModel):
    """Schema for updating a Form Type."""

    form_name: Optional[str] = Field(None, min_length=1, max_length=255)
    version: Optional[str] = Field(None, pattern=r"^\d{1,3}\.\d{1,3}\.\d{1,3}$")
    schema: Optional[Dict[str, Any]] = None


class FormTypeResponse(BaseModel):
    """Schema for Form Type response."""

    form_type_id: str
    form_name: str
    stage_id: str
    form_path: str
    version: str
    schema_reference: Optional[str] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FormTypeWithSchema(FormTypeResponse):
    """Schema for Form Type with schema."""

    schema_data: Optional[Dict[str, Any]] = None
