"""Permission API endpoints."""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.auth import get_current_user
from src.app.database import get_db
from src.app.models.user import User
from src.app.schemas.permission import (
    CategoryPermissionCreate,
    CategoryPermissionResponse,
    FormTypePermissionCreate,
    FormTypePermissionResponse,
    ProjectRoleAssignmentResponse,
    RoleCreate,
    RoleResponse,
    RoleSetCreate,
    RoleSetResponse,
    RoleSetUpdate,
    StagePermissionCreate,
    StagePermissionResponse,
    StageAndFormTypePermissionsResponse,
    UserAccessResponse,
    UserProjectRoleCreate,
    UserProjectRoleResponse,
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
    """Get all permissions configured for a specific stage, its category
    permissions, and its linked form types."""
    from src.app.models.permission import CategoryPermission, StagePermission, FormTypePermission
    from src.app.models.stage_form_type import StageFormType
    from sqlalchemy import select

    # Get stage permissions
    stage_res = await db.execute(
        select(StagePermission).where(StagePermission.stage_id == stage_id)
    )
    stage_permissions = stage_res.scalars().all()

    # Get category permissions for this stage
    category_res = await db.execute(
        select(CategoryPermission).where(CategoryPermission.stage_id == stage_id)
    )
    category_permissions = category_res.scalars().all()

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
        category_permissions=[CategoryPermissionResponse.model_validate(p) for p in category_permissions],
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
    - **can_create_records**: Can create form records
    - **can_edit**: Can edit the form type definition
    - **can_delete**: Can delete the form type definition
    - **can_edit_records**: Can edit form records
    - **can_delete_records**: Can delete form records
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


# Category Permissions (project/stage + FormType.group)
@router.post(
    "/stages/{stage_id}/categories/{category}",
    response_model=CategoryPermissionResponse,
    status_code=201,
)
async def grant_category_permission(
    stage_id: str,
    category: str,
    permission_data: CategoryPermissionCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Grant a FormType-category permission to a role, scoped to a project (stage).

    Sits between stage and individual form-type permissions: applies to
    every form type whose `group` matches `category`, within this stage's
    subtree.
    """
    service = PermissionService(db)
    try:
        return await service.grant_category_permission(
            stage_id, category, permission_data, granted_by="system"
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/stages/{stage_id}/categories/{category}/roles/{role_name}")
async def revoke_category_permission(
    stage_id: str,
    category: str,
    role_name: str,
    location_id: Optional[str] = Query(None),
    department_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a category permission from a role."""
    service = PermissionService(db)
    try:
        return await service.revoke_category_permission(
            stage_id, category, role_name, location_id, department_id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/categories", response_model=List[CategoryPermissionResponse])
async def list_category_permissions(
    stage_id: Optional[str] = Query(None),
    category: Optional[str] = Query(None),
    role_name: Optional[str] = Query(None),
    location_id: Optional[str] = Query(None),
    department_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    """List category permissions, optionally filtered by stage, category, role, location, and department."""
    service = PermissionService(db)
    return await service.list_category_permissions(
        stage_id, category, role_name, location_id, department_id
    )


# User Project Roles
@router.post("/users/roles", status_code=201)
async def assign_user_role(
    role_data: UserProjectRoleCreate, db: AsyncSession = Depends(get_db)
):
    """Assign a role to a user, scoped to a project (stage) — or globally
    when stage_id is omitted."""
    service = PermissionService(db)
    try:
        return await service.assign_user_role(role_data, assigned_by="system")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/users/{user_id}/roles/{role_name}")
async def revoke_user_project_role(
    user_id: str,
    role_name: str,
    stage_id: Optional[str] = Query(None, description="Omit to revoke the global assignment"),
    db: AsyncSession = Depends(get_db),
):
    """Revoke a specific (user, project, role) assignment. Omit stage_id to
    revoke the global assignment for that role."""
    service = PermissionService(db)
    try:
        return await service.revoke_project_role(user_id, role_name, stage_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/users/{user_id}/project-roles", response_model=List[UserProjectRoleResponse])
async def list_user_project_roles(user_id: str, db: AsyncSession = Depends(get_db)):
    """List all of a user's (project, role) assignment rows, including global grants."""
    service = PermissionService(db)
    return await service.list_user_project_roles(user_id)


@router.get("/stages/{stage_id}/members", response_model=List[ProjectRoleAssignmentResponse])
async def list_stage_members(stage_id: str, db: AsyncSession = Depends(get_db)):
    """List users with effective access to this stage: direct grants on this
    stage, grants inherited from ancestor projects, and global grants."""
    service = PermissionService(db)
    try:
        return await service.list_stage_members(stage_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


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
async def get_user_roles(
    user_id: str,
    stage_id: Optional[str] = Query(
        None, description="If given, only roles effective on this project/stage (global + this stage or its ancestors)"
    ),
    db: AsyncSession = Depends(get_db),
):
    """Get roles for a user. Without stage_id: the union of all roles held
    anywhere. With stage_id: only roles effective there (role-assignment cascade)."""
    service = PermissionService(db)
    roles = await service.get_user_roles(user_id, stage_id=stage_id)
    return {"user_id": user_id, "stage_id": stage_id, "roles": roles}


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


# RoleSets — reusable per-stage governing role bundles
@router.post("/role-sets", response_model=RoleSetResponse, status_code=201)
async def create_role_set(
    data: RoleSetCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Create a new RoleSet — a named, reusable bundle of roles that a
    stage can point to as its governing set."""
    service = PermissionService(db)
    try:
        return await service.create_role_set(data, created_by=current_user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/role-sets", response_model=List[RoleSetResponse])
async def list_role_sets(db: AsyncSession = Depends(get_db)):
    """List all RoleSets with their member roles."""
    service = PermissionService(db)
    return await service.list_role_sets()


@router.put("/role-sets/{role_set_id}", response_model=RoleSetResponse)
async def update_role_set(
    role_set_id: str, data: RoleSetUpdate, db: AsyncSession = Depends(get_db)
):
    """Update a RoleSet's name/description, or fully replace its role
    membership (when role_names is given)."""
    service = PermissionService(db)
    try:
        return await service.update_role_set(role_set_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/role-sets/{role_set_id}")
async def delete_role_set(role_set_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a RoleSet. Stages pointing at it fall back to inheritance
    from their nearest ancestor's RoleSet."""
    service = PermissionService(db)
    try:
        return await service.delete_role_set(role_set_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
