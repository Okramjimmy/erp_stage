"""Pydantic schemas for Workflow Assignment CRUD."""

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel


class WorkflowAssignmentCreate(BaseModel):
    stage_id: str
    form_type_id: str
    role: str
    user_id: str


class WorkflowAssignmentUpdate(BaseModel):
    user_id: str


class WorkflowAssignmentResponse(BaseModel):
    assignment_id: UUID
    stage_id: str
    form_type_id: str
    role: str
    user_id: str
    assigned_by: Optional[str] = None
    active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class WorkflowAssignmentList(BaseModel):
    items: List[WorkflowAssignmentResponse]
    total: int
