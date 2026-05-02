"""FormType API endpoints."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.database import get_db
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
    form_data: FormTypeCreate, db: AsyncSession = Depends(get_db)
):
    """
    Create a new form type.

    - **form_name**: Name of the form
    - **stage_id**: Parent stage ID
    - **version**: Form version (e.g., 1.0.0)
    - **schema**: Optional form schema definition
    """
    service = FormTypeService(db)
    try:
        return await service.create_form_type(form_data, created_by="system")
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
    db: AsyncSession = Depends(get_db),
):
    """Update a form type."""
    service = FormTypeService(db)
    try:
        return await service.update_form_type(form_type_id, form_data)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{form_type_id}")
async def delete_form_type(form_type_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a form type."""
    service = FormTypeService(db)
    try:
        result = await service.delete_form_type(form_type_id)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
