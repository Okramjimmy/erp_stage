from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class FormTypeBase(BaseModel):
    """Base schema for Form Type."""

    form_name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    version: str = Field(default="1.0.0", pattern=r"^\d{1,3}\.\d{1,3}\.\d{1,3}$")


class FormTypeCreate(FormTypeBase):
    """Schema for creating a Form Type."""

    schema: Optional[Dict[str, Any]] = Field(default=None, alias="schema_reference")
    workflow_data: Optional[Dict[str, Any]] = None

    model_config = {
        "populate_by_name": True
    }

    @model_validator(mode='before')
    @classmethod
    def map_schema_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if 'schema' in data and 'schema_reference' not in data:
                data['schema_reference'] = data['schema']
            elif 'schema_reference' in data and 'schema' not in data:
                data['schema'] = data['schema_reference']
        return data


class FormTypeUpdate(BaseModel):
    """Schema for updating a Form Type."""

    form_name: Optional[str] = Field(None, min_length=1, max_length=255)
    version: Optional[str] = Field(None, pattern=r"^\d{1,3}\.\d{1,3}\.\d{1,3}$")
    schema: Optional[Dict[str, Any]] = Field(default=None, alias="schema_reference")
    workflow_data: Optional[Dict[str, Any]] = None

    model_config = {
        "populate_by_name": True
    }

    @model_validator(mode='before')
    @classmethod
    def map_schema_fields(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if 'schema' in data and 'schema_reference' not in data:
                data['schema_reference'] = data['schema']
            elif 'schema_reference' in data and 'schema' not in data:
                data['schema'] = data['schema_reference']
        return data


class FormTypeResponse(BaseModel):
    """Schema for Form Type response."""

    form_type_id: str
    form_name: str
    description: Optional[str] = None
    version: str
    schema_reference: Optional[Dict[str, Any]] = None  # JSONB type - accepts dict directly
    workflow_data: Optional[Dict[str, Any]] = None
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    @field_validator("schema_reference", mode="before")
    @classmethod
    def parse_schema_reference(cls, v):
        if v == "null":
            return None
        if isinstance(v, str):
            try:
                import json
                parsed = json.loads(v)
                if parsed is None or isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
        return v


class FormTypeWithSchema(FormTypeResponse):
    """Schema for Form Type with schema (backwards compatible alias)."""

    schema_data: Optional[Dict[str, Any]] = Field(
        default=None,
        alias="schema_reference",
        description="Alias for schema_reference for backwards compatibility"
    )

    @field_validator("schema_data", mode="before")
    @classmethod
    def parse_schema_data(cls, v):
        if v == "null":
            return None
        if isinstance(v, str):
            try:
                import json
                parsed = json.loads(v)
                if parsed is None or isinstance(parsed, dict):
                    return parsed
            except Exception:
                pass
        return v
