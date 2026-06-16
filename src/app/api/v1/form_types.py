"""FormType API endpoints."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.auth import get_current_user
from src.app.database import get_db
from src.app.models.user import User
from src.app.schemas.form_type import (
    FormTypeCreate,
    FormTypeResponse,
    FormTypeUpdate,
    FormTypeWithSchema,
)
from src.app.services.form_type_service import FormTypeService

router = APIRouter(prefix="/form-types", tags=["Form Types"])


@router.post("", response_model=FormTypeResponse, status_code=201)
async def create_form_type(
    form_data: FormTypeCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new form type.

    The created_by field is automatically set from the authenticated user.

    - **form_name**: Name of the form (must be unique)
    - **description**: Optional description
    - **version**: Form version (e.g., 1.0.0)
    - **schema**: Optional form schema definition
    """
    from src.app.services.permission_service import PermissionService
    perm_service = PermissionService(db)
    if not await perm_service.is_superadmin(current_user.user_id):
        raise HTTPException(status_code=403, detail="Only superadmins can create Form Types.")

    service = FormTypeService(db)
    try:
        return await service.create_form_type(form_data, created_by=current_user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{form_type_id}/link-stage/{stage_id}", status_code=200)
async def link_form_to_stage(
    form_type_id: str,
    stage_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Link a form type to a stage."""
    from src.app.services.permission_service import PermissionService
    perm_service = PermissionService(db)
    if not await perm_service.check_stage_permission(current_user.user_id, stage_id, "can_edit"):
        raise HTTPException(status_code=403, detail="Permission denied to link form types to this stage.")

    service = FormTypeService(db)
    try:
        return await service.link_form_to_stage(
            form_type_id=form_type_id, 
            stage_id=stage_id, 
            linked_by=current_user.user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{form_type_id}/link-stage/{stage_id}", status_code=200)
async def unlink_form_from_stage(
    form_type_id: str,
    stage_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Unlink a form type from a stage."""
    from src.app.services.permission_service import PermissionService
    perm_service = PermissionService(db)
    if not await perm_service.check_stage_permission(current_user.user_id, stage_id, "can_edit"):
        raise HTTPException(status_code=403, detail="Permission denied to unlink form types from this stage.")

    service = FormTypeService(db)
    try:
        return await service.unlink_form_from_stage(
            form_type_id=form_type_id, 
            stage_id=stage_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=List[FormTypeResponse])
async def list_form_types(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """List all form types with pagination."""
    service = FormTypeService(db)
    return await service.get_all_form_types(skip=skip, limit=limit)


@router.get("/with-schema", response_model=List[FormTypeWithSchema])
async def list_form_types_with_schema(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """List all form types with schema data for template selection."""
    service = FormTypeService(db)
    return await service.get_all_form_types_with_schema(skip=skip, limit=limit)


@router.get("/search", response_model=List[FormTypeResponse])
async def search_form_types(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Search form types by name."""
    service = FormTypeService(db)
    return await service.search_form_types(query=q, limit=limit)


@router.get("/stage/{stage_id}", response_model=List[FormTypeResponse])
async def get_form_types_by_stage(
    stage_id: str,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Get all form types for a specific stage."""
    service = FormTypeService(db)
    return await service.get_form_types_by_stage(stage_id, skip=skip, limit=limit)


@router.get("/{form_type_id}", response_model=FormTypeResponse)
async def get_form_type(form_type_id: str, db: AsyncSession = Depends(get_db)):
    """Get a specific form type by ID."""
    service = FormTypeService(db)
    form_type = await service.get_form_type(form_type_id)
    if not form_type:
        raise HTTPException(
            status_code=404, detail=f"FormType {form_type_id} not found"
        )
    return form_type


@router.get("/{form_type_id}/schema", response_model=FormTypeWithSchema)
async def get_form_type_with_schema(
    form_type_id: str, db: AsyncSession = Depends(get_db)
):
    """Get form type with schema data."""
    service = FormTypeService(db)
    form_type = await service.get_form_type_with_schema(form_type_id)
    if not form_type:
        raise HTTPException(
            status_code=404, detail=f"FormType {form_type_id} not found"
        )
    return form_type


@router.put("/{form_type_id}", response_model=FormTypeResponse)
async def update_form_type(
    form_type_id: str,
    form_data: FormTypeUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update a form type."""
    from src.app.services.permission_service import PermissionService
    perm_service = PermissionService(db)
    if not await perm_service.check_form_type_permission(current_user.user_id, form_type_id, "can_edit"):
        raise HTTPException(status_code=403, detail="Permission denied to edit this form type.")

    service = FormTypeService(db)
    try:
        return await service.update_form_type(form_type_id, form_data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/{form_type_id}/settings", response_model=FormTypeResponse)
async def update_form_settings_only(
    form_type_id: str,
    settings_data: dict,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update only the settings (is_submittable / is_child_table) of a form type."""
    from src.app.services.permission_service import PermissionService
    perm_service = PermissionService(db)
    if not await perm_service.check_form_type_permission(current_user.user_id, form_type_id, "can_edit"):
        raise HTTPException(status_code=403, detail="Permission denied to edit this form type.")

    from src.app.models.form_type import FormType
    form_type_obj = await db.get(FormType, form_type_id)
    if not form_type_obj:
        raise HTTPException(status_code=404, detail="Form type not found")

    schema_ref = form_type_obj.schema_reference or {}
    if not isinstance(schema_ref, dict):
        schema_ref = {}
    
    settings_dict = schema_ref.setdefault("settings", {})
    if not isinstance(settings_dict, dict):
        settings_dict = {}
        schema_ref["settings"] = settings_dict

    if "is_submittable" in settings_data:
        settings_dict["is_submittable"] = bool(settings_data["is_submittable"])
    if "is_child_table" in settings_data:
        settings_dict["is_child_table"] = bool(settings_data["is_child_table"])

    from sqlalchemy.orm.attributes import flag_modified
    form_type_obj.schema_reference = schema_ref
    flag_modified(form_type_obj, "schema_reference")
    
    await db.commit()
    await db.refresh(form_type_obj)
    return form_type_obj



@router.delete("/{form_type_id}")
async def delete_form_type(
    form_type_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Delete a form type."""
    from src.app.services.permission_service import PermissionService
    permission_service = PermissionService(db)
    has_permission = await permission_service.check_form_type_permission(
        user_id=current_user.user_id,
        form_type_id=form_type_id,
        permission_type="can_delete"
    )
    if not has_permission:
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to delete this form type"
        )

    service = FormTypeService(db)
    try:
        result = await service.delete_form_type(form_type_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
