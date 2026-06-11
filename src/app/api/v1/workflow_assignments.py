"""API endpoints for Workflow Assignment CRUD."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.auth import get_current_user
from src.app.database import get_db
from src.app.models.user import User
from src.app.schemas.workflow_assignment import (
    WorkflowAssignmentCreate,
    WorkflowAssignmentList,
    WorkflowAssignmentResponse,
    WorkflowAssignmentUpdate,
)
from src.app.services.workflow_assignment_service import WorkflowAssignmentService

router = APIRouter(prefix="/workflow-assignments", tags=["Workflow Assignments"])


@router.post("", response_model=WorkflowAssignmentResponse, status_code=201)
async def create_assignment(
    payload: WorkflowAssignmentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Assign a user to a role for a specific stage + form type."""
    svc = WorkflowAssignmentService(db)
    try:
        return await svc.create_assignment(payload, assigned_by=current_user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=WorkflowAssignmentList)
async def list_assignments(
    stage_id: str = Query(...),
    form_type_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """List all active assignments for a stage + form type."""
    svc = WorkflowAssignmentService(db)
    items = await svc.get_assignments(stage_id, form_type_id)
    return WorkflowAssignmentList(items=items, total=len(items))


@router.put("/{assignment_id}", response_model=WorkflowAssignmentResponse)
async def update_assignment(
    assignment_id: UUID,
    payload: WorkflowAssignmentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update the user assigned to an existing assignment."""
    svc = WorkflowAssignmentService(db)
    try:
        return await svc.update_assignment(assignment_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{assignment_id}", status_code=204)
async def delete_assignment(
    assignment_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Delete a workflow assignment."""
    svc = WorkflowAssignmentService(db)
    try:
        await svc.delete_assignment(assignment_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
