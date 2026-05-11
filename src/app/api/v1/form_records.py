from typing import List

from fastapi import APIRouter, Depends, Form, HTTPException, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.database import get_db
from src.app.schemas.form_record import (
    FormRecordCreate,
    FormRecordList,
    FormRecordResponse,
    FormRecordUpdate,
)
from src.app.services.form_record_service import FormRecordService

router = APIRouter(prefix="/form-records", tags=["Form Records"])


@router.post("", response_model=FormRecordResponse, status_code=201)
async def create_record(payload: FormRecordCreate, db: AsyncSession = Depends(get_db)):
    svc = FormRecordService(db)
    try:
        return await svc.create(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=FormRecordList)
async def list_records(
    form_type_id: str = Query(...),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    svc = FormRecordService(db)
    items, total = await svc.list_by_form_type(form_type_id, skip=skip, limit=limit)
    return FormRecordList(items=items, total=total)


@router.get("/{record_id}", response_model=FormRecordResponse)
async def get_record(record_id: str, db: AsyncSession = Depends(get_db)):
    svc = FormRecordService(db)
    rec = await svc.get(record_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Record not found")
    return rec


@router.put("/{record_id}", response_model=FormRecordResponse)
async def update_record(
    record_id: str, payload: FormRecordUpdate, db: AsyncSession = Depends(get_db)
):
    svc = FormRecordService(db)
    try:
        return await svc.update(record_id, payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{record_id}/submit", response_model=FormRecordResponse)
async def submit_record(record_id: str, db: AsyncSession = Depends(get_db)):
    svc = FormRecordService(db)
    try:
        return await svc.submit(record_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{record_id}/cancel", response_model=FormRecordResponse)
async def cancel_record(record_id: str, db: AsyncSession = Depends(get_db)):
    svc = FormRecordService(db)
    try:
        return await svc.cancel(record_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{record_id}/amend", response_model=FormRecordResponse)
async def amend_record(record_id: str, db: AsyncSession = Depends(get_db)):
    svc = FormRecordService(db)
    try:
        return await svc.amend(record_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post(
    "/{record_id}/upload-attachment",
    response_model=FormRecordResponse,
    summary="Upload a file for an Attach/Attach Image field",
    description=(
        "Accepts a multipart/form-data request with the file and the target field name. "
        "The file is stored in MinIO at `stage_id/form_name/field_label/filename` and "
        "the resulting path is saved into `record.data[field_name]`."
    ),
)
async def upload_attachment(
    record_id: str,
    field_name: str | None = Form(None, description="Name of the Attach field in the form schema"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    svc = FormRecordService(db)
    try:
        if not field_name:
            raise HTTPException(status_code=400, detail="Field name is required")
        file_bytes = await file.read()
        return await svc.upload_attachment(
            record_id=record_id,
            field_name=field_name,
            file_bytes=file_bytes,
            filename=file.filename,
            content_type=file.content_type or "application/octet-stream",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{record_id}", status_code=204)
async def delete_record(record_id: str, db: AsyncSession = Depends(get_db)):
    svc = FormRecordService(db)
    try:
        await svc.delete(record_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
