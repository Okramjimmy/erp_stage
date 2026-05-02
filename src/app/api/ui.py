"""UI routes — renders Jinja2 HTML templates."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.database import get_db
from src.app.services.form_record_service import FormRecordService
from src.app.services.form_type_service import FormTypeService
from src.app.services.stage_service import StageService

templates = Jinja2Templates(directory="templates")
router = APIRouter(tags=["UI"])


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    stage_service = StageService(db)
    ft_service = FormTypeService(db)

    tree = await stage_service.get_stage_tree()
    stages = await stage_service.get_all_stages(limit=200)
    form_types = await ft_service.get_all_form_types(limit=200)

    return templates.TemplateResponse("index.html", {
        "request": request,
        "tree": tree,
        "stages": stages,
        "form_types": form_types,
        "total_stages": len(stages),
        "total_forms": len(form_types),
    })


@router.get("/stages/{stage_id}", response_class=HTMLResponse)
async def stage_detail(
    request: Request, stage_id: str, db: AsyncSession = Depends(get_db)
):
    stage_service = StageService(db)
    stage = await stage_service.get_stage(stage_id)
    if not stage:
        return HTMLResponse("Stage not found", status_code=404)

    ft_service = FormTypeService(db)
    form_types = await ft_service.get_form_types_by_stage(stage_id)

    all_stages = await stage_service.get_all_stages(limit=500)
    children = [s for s in all_stages if s.parent_stage_id == stage_id]
    all_stages_for_move = [s for s in all_stages if s.stage_id != stage_id]

    # Build breadcrumb from lineage
    breadcrumb = []
    for ancestor_id in stage.lineage_path:
        ancestor = await stage_service.get_stage(ancestor_id)
        if ancestor:
            breadcrumb.append(ancestor)

    return templates.TemplateResponse("stage_detail.html", {
        "request": request,
        "stage": stage,
        "form_types": form_types,
        "children": children,
        "breadcrumb": breadcrumb,
        "all_stages": all_stages_for_move,
    })


@router.get("/form-builder/new/{stage_id}", response_class=HTMLResponse)
async def new_form_builder(
    request: Request, stage_id: str, db: AsyncSession = Depends(get_db)
):
    stage_service = StageService(db)
    stage = await stage_service.get_stage(stage_id)
    if not stage:
        return HTMLResponse("Stage not found", status_code=404)

    return templates.TemplateResponse("form_builder.html", {
        "request": request,
        "form_type": None,
        "stage": stage,
    })


@router.get("/form-builder/{form_type_id}", response_class=HTMLResponse)
async def form_builder(
    request: Request, form_type_id: str, db: AsyncSession = Depends(get_db)
):
    ft_service = FormTypeService(db)
    form_type = await ft_service.get_form_type_with_schema(form_type_id)
    if not form_type:
        return HTMLResponse("Form type not found", status_code=404)

    stage_service = StageService(db)
    stage = await stage_service.get_stage(form_type.stage_id)

    return templates.TemplateResponse("form_builder.html", {
        "request": request,
        "form_type": form_type,
        "stage": stage,
    })


@router.get("/forms/{form_type_id}/new", response_class=HTMLResponse)
async def new_form_view(
    request: Request, form_type_id: str, db: AsyncSession = Depends(get_db)
):
    ft_service = FormTypeService(db)
    form_type = await ft_service.get_form_type_with_schema(form_type_id)
    if not form_type:
        return HTMLResponse("Form type not found", status_code=404)
    stage_service = StageService(db)
    stage = await stage_service.get_stage(form_type.stage_id)
    return templates.TemplateResponse("form_view.html", {
        "request": request,
        "form_type": form_type,
        "stage": stage,
        "record": None,
    })


@router.get("/forms/{form_type_id}/{record_id}", response_class=HTMLResponse)
async def edit_form_view(
    request: Request, form_type_id: str, record_id: str, db: AsyncSession = Depends(get_db)
):
    ft_service = FormTypeService(db)
    form_type = await ft_service.get_form_type_with_schema(form_type_id)
    if not form_type:
        return HTMLResponse("Form type not found", status_code=404)
    svc = FormRecordService(db)
    record = await svc.get(record_id)
    if not record:
        return HTMLResponse("Record not found", status_code=404)
    stage_service = StageService(db)
    stage = await stage_service.get_stage(form_type.stage_id)
    return templates.TemplateResponse("form_view.html", {
        "request": request,
        "form_type": form_type,
        "stage": stage,
        "record": record,
    })


@router.get("/forms/{form_type_id}", response_class=HTMLResponse)
async def list_form_view(
    request: Request, form_type_id: str, db: AsyncSession = Depends(get_db)
):
    ft_service = FormTypeService(db)
    form_type = await ft_service.get_form_type_with_schema(form_type_id)
    if not form_type:
        return HTMLResponse("Form type not found", status_code=404)
    svc = FormRecordService(db)
    items, total = await svc.list_by_form_type(form_type_id, limit=100)
    stage_service = StageService(db)
    stage = await stage_service.get_stage(form_type.stage_id)
    return templates.TemplateResponse("form_list.html", {
        "request": request,
        "form_type": form_type,
        "stage": stage,
        "records": items,
        "total": total,
    })
