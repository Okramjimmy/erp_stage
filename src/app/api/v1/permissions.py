"""Permission API endpoints."""

from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.database import get_db
from src.app.schemas.permission import (
    FormTypePermissionCreate,
    FormTypePermissionResponse,
    StagePermissionCreate,
    StagePermissionResponse,
    UserAccessResponse,
    UserRoleCreate,
)
from src.app.services.permission_service import PermissionService

router = APIRouter(prefix="/permissions", tags=["Permissions"])


# Stage Permissions
@router.post(
    "/stages/{stage_id}", response_model=StagePermissionResponse, status_code=201
)
async def grant_stage_permission(
    stage_id: str,
    permission_data: StagePermissionCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Grant stage permission to a role.

    - **role_name**: Role to grant permission to
    - **can_view**: Can view the stage
    - **can_create**: Can create children/form types
    - **can_edit**: Can edit the stage
    - **can_delete**: Can delete the stage
    - **can_manage_permissions**: Can manage permissions on this stage
    """
    service = PermissionService(db)
    try:
        return await service.grant_stage_permission(
            stage_id, permission_data, granted_by="system"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/stages/{stage_id}/roles/{role_name}")
async def revoke_stage_permission(
    stage_id: str, role_name: str, db: AsyncSession = Depends(get_db)
):
    """Revoke stage permission from a role."""
    service = PermissionService(db)
    try:
        result = await service.revoke_stage_permission(stage_id, role_name)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# Form Type Permissions
@router.post(
    "/form-types/{form_type_id}",
    response_model=FormTypePermissionResponse,
    status_code=201,
)
async def grant_form_type_permission(
    form_type_id: str,
    permission_data: FormTypePermissionCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Grant form type permission to a role.

    - **role_name**: Role to grant permission to
    - **can_view**: Can view the form type
    - **can_create**: Can create form instances
    - **can_edit**: Can edit the form type
    - **can_delete**: Can delete the form type
    - **can_submit**: Can submit forms
    - **can_manage_permissions**: Can manage permissions
    """
    service = PermissionService(db)
    try:
        return await service.grant_form_type_permission(
            form_type_id, permission_data, granted_by="system"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# User Roles
@router.post("/users/roles", status_code=201)
async def assign_user_role(
    role_data: UserRoleCreate, db: AsyncSession = Depends(get_db)
):
    """Assign a role to a user."""
    service = PermissionService(db)
    result = await service.assign_user_role(role_data, assigned_by="system")
    return result


@router.get("/users/{user_id}/roles")
async def get_user_roles(user_id: str, db: AsyncSession = Depends(get_db)):
    """Get all roles for a user."""
    service = PermissionService(db)
    roles = await service.get_user_roles(user_id)
    return {"user_id": user_id, "roles": roles}


# Access Control
@router.get("/users/{user_id}/accessible-stages", response_model=UserAccessResponse)
async def get_user_accessible_stages(user_id: str, db: AsyncSession = Depends(get_db)):
    """
    Get all accessible stages for a user using lineage-based visibility.

    A user can see:
    - Stages where they have direct permission
    - All descendants of those stages (via lineage)
    """
    service = PermissionService(db)
    return await service.get_user_accessible_resources(user_id)


@router.get("/users/{user_id}/check-stage/{stage_id}")
async def check_stage_permission(
    user_id: str,
    stage_id: str,
    permission_type: str = Query(
        "can_view",
        regex="^can_view|can_create|can_edit|can_delete|can_manage_permissions$",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Check if user has specific permission on a stage.

    Uses lineage-based visibility: user has permission on stage if
    they have permission on ANY ancestor of the stage.
    """
    service = PermissionService(db)
    has_permission = await service.check_stage_permission(
        user_id, stage_id, permission_type
    )
    return {
        "user_id": user_id,
        "stage_id": stage_id,
        "permission_type": permission_type,
        "has_permission": has_permission,
    }
