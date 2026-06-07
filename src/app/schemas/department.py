"""Pydantic schemas for Department endpoints."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class DepartmentBase(BaseModel):
    """Base schema for Department."""

    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None


class DepartmentCreate(DepartmentBase):
    """Schema for creating a Department."""
    pass


class DepartmentUpdate(BaseModel):
    """Schema for updating a Department."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None


class DepartmentResponse(DepartmentBase):
    """Schema for Department response."""

    department_id: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True
