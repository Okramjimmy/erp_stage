"""Permission API endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.auth import get_current_user
from src.app.database import get_db
from src.app.models.user import User
from src.app.schemas.permission import (
    FormTypePermissionCreate,
    FormTypePermissionResponse,
    RoleCreate,
    RoleResponse,
    StagePermissionCreate,
    StagePermissionResponse,
    StageAndFormTypePermissionsResponse,
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
    stage_id: str,
    role_name: str,
    location_id: Optional[str] = Query(None),
    department_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Revoke stage permission from a role."""
    service = PermissionService(db)
    try:
        result = await service.revoke_stage_permission(
            stage_id, role_name, location_id, department_id
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/stages/{stage_id}", response_model=StageAndFormTypePermissionsResponse)
async def get_stage_permissions(
    stage_id: str, db: AsyncSession = Depends(get_db)
):
    """Get all permissions configured for a specific stage and its linked form types."""
    from src.app.models.permission import StagePermission, FormTypePermission
    from src.app.models.stage_form_type import StageFormType
    from sqlalchemy import select
    
    # Get stage permissions
    stage_res = await db.execute(
        select(StagePermission).where(StagePermission.stage_id == stage_id)
    )
    stage_permissions = stage_res.scalars().all()
    
    # Get form type permissions for form types linked to this stage
    ft_res = await db.execute(
        select(FormTypePermission).where(
            FormTypePermission.form_type_id.in_(
                select(StageFormType.form_type_id).where(StageFormType.stage_id == stage_id)
            )
        )
    )
    form_type_permissions = ft_res.scalars().all()

    return StageAndFormTypePermissionsResponse(
        stage_permissions=[StagePermissionResponse.model_validate(p) for p in stage_permissions],
        form_type_permissions=[FormTypePermissionResponse.model_validate(p) for p in form_type_permissions]
    )


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


@router.delete("/form-types/{form_type_id}/roles/{role_name}")
async def revoke_form_type_permission(
    form_type_id: str,
    role_name: str,
    location_id: Optional[str] = Query(None),
    department_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Revoke form type permission from a role."""
    service = PermissionService(db)
    try:
        result = await service.revoke_form_type_permission(
            form_type_id, role_name, location_id, department_id
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# User Roles
@router.post("/users/roles", status_code=201)
async def assign_user_role(
    role_data: UserRoleCreate, db: AsyncSession = Depends(get_db)
):
    """Assign a role to a user."""
    service = PermissionService(db)
    result = await service.assign_user_role(role_data, assigned_by="system")
    return result


# Role Management
@router.post("/roles", response_model=RoleResponse, status_code=201)
async def create_role(
    role_data: RoleCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new role.

    - **role_name**: Unique role name (lowercase letters, numbers, underscores only)
    - **description**: Optional description of the role

    The created_by field is automatically set from the authenticated user.
    """
    service = PermissionService(db)
    try:
        return await service.create_role(role_data, created_by=current_user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


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


# List all permissions
@router.get("/stages", response_model=List[StagePermissionResponse])
async def list_stage_permissions(
    role_name: Optional[str] = Query(None),
    location_id: Optional[str] = Query(None),
    department_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """List all stage permissions, optionally filtered by role, location, and department."""
    service = PermissionService(db)
    return await service.list_stage_permissions(role_name, location_id, department_id)


@router.get("/form-types", response_model=List[FormTypePermissionResponse])
async def list_form_type_permissions(
    role_name: Optional[str] = Query(None),
    location_id: Optional[str] = Query(None),
    department_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """List all form type permissions, optionally filtered by role, location, and department."""
    service = PermissionService(db)
    return await service.list_form_type_permissions(role_name, location_id, department_id)


@router.get("/roles/{role_name}")
async def get_role_permissions(role_name: str, db: AsyncSession = Depends(get_db)):
    """Get all permissions for a specific role."""
    service = PermissionService(db)
    return await service.get_role_permissions(role_name)


# Roles Management
@router.get("/roles")
async def list_all_roles(db: AsyncSession = Depends(get_db)):
    """List all unique roles in the system."""
    service = PermissionService(db)
    return await service.list_all_roles()


@router.delete("/roles/{role_name}")
async def delete_role(role_name: str, db: AsyncSession = Depends(get_db)):
    """Delete a role and all its associated permissions."""
    service = PermissionService(db)
    return await service.delete_role(role_name)


@router.put("/roles/{old_role_name}")
async def rename_role(
    old_role_name: str,
    new_role_name: str = Query(..., min_length=1, max_length=100),
    db: AsyncSession = Depends(get_db),
):
    """Rename a role."""
    service = PermissionService(db)
    return await service.rename_role(old_role_name, new_role_name)
