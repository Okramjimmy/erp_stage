from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class FormTypeBase(BaseModel):
    """Base schema for Form Type."""

    form_name: str = Field(..., min_length=1, max_length=255)
    stage_id: str = Field(..., min_length=1)
    version: str = Field(default="1.0.0", pattern=r"^\d{1,3}\.\d{1,3}\.\d{1,3}$")


class FormTypeCreate(FormTypeBase):
    """Schema for creating a Form Type."""

    schema: Optional[Dict[str, Any]] =Field(default=None, alias="schema_reference")

    @model_validator(mode='after')
    def map_schema_to_reference(self):
        """Map schema field to schema_reference for JSONB storage."""
        if self.schema is not None:
            # Since schema_reference is not in the base class, we'll handle it in the service
            pass
        return self


class FormTypeUpdate(BaseModel):
    """Schema for updating a Form Type."""

    form_name: Optional[str] = Field(None, min_length=1, max_length=255)
    version: Optional[str] = Field(None, pattern=r"^\d{1,3}\.\d{1,3}\.\d{1,3}$")
    schema: Optional[Dict[str, Any]] = None  # Alias for schema_reference


class FormTypeResponse(BaseModel):
    """Schema for Form Type response."""

    form_type_id: str
    form_name: str
    stage_id: str
    form_path: str
    version: str
    schema_reference: Optional[Dict[str, Any]] = None  # JSONB type - accepts dict directly
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class FormTypeWithSchema(FormTypeResponse):
    """Schema for Form Type with schema (backwards compatible alias)."""

    schema_data: Optional[Dict[str, Any]] = Field(
        default=None,
        alias="schema_reference",
        description="Alias for schema_reference for backwards compatibility"
    )
