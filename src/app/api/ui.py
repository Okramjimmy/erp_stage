"""UI routes — renders Jinja2 HTML templates."""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.auth import get_current_user, get_current_user_optional, _require_auth
from src.app.database import get_db
from src.app.services.form_record_service import FormRecordService
from src.app.services.form_type_service import FormTypeService
from src.app.services.stage_service import StageService
from src.app.services.user_service import UserService

templates = Jinja2Templates(directory="/app/src/templates", auto_reload=True)
router = APIRouter(tags=["UI"])


# ---------------------------------------------------------------------------
# Auth pages (no login required)
# ---------------------------------------------------------------------------

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Show login page. Redirect to dashboard if already authenticated."""
    from src.app.core.auth import get_current_user_optional, clear_session
    user = await get_current_user_optional(request, db)
    if user:
        return RedirectResponse(url="/", status_code=302)
    clear_session(request)
    return templates.TemplateResponse("login.html", {"request": request})


@router.get("/logout")
async def logout(request: Request):
    """Clear session and redirect to login."""
    from src.app.core.auth import clear_session
    clear_session(request)
    return RedirectResponse(url="/login", status_code=302)


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    user, roles = await _require_auth(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    stage_service = StageService(db)
    ft_service = FormTypeService(db)

    tree = await stage_service.get_stage_tree(user_id=user.user_id)
    
    from src.app.services.permission_service import PermissionService
    perm_service = PermissionService(db)
    visible_stage_ids = set(await perm_service.get_visible_stages(user.user_id, user.is_superadmin))
    
    stages = [s for s in await stage_service.get_all_stages(limit=200) if s.stage_id in visible_stage_ids]
    form_types = [ft for ft in await ft_service.get_all_form_types(limit=200) if ft.stage_id in visible_stage_ids]

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "tree": tree,
            "stages": stages,
            "form_types": form_types,
            "total_stages": len(stages),
            "total_forms": len(form_types),
            "current_user": user,
            "current_user_roles": roles,
        },
    )


# ---------------------------------------------------------------------------
# Stage detail
# ---------------------------------------------------------------------------

@router.get("/stages/{stage_id}", response_class=HTMLResponse)
async def stage_detail(
    request: Request, stage_id: str, db: AsyncSession = Depends(get_db)
):
    user, roles = await _require_auth(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    stage_service = StageService(db)
    stage = await stage_service.get_stage(stage_id)
    if not stage:
        return HTMLResponse("Stage not found", status_code=404)

    ft_service = FormTypeService(db)
    form_types = await ft_service.get_form_types_by_stage(stage_id)

    all_stages = await stage_service.get_all_stages(limit=500)
    children = [s for s in all_stages if s.parent_stage_id == stage_id]
    all_stages_for_move = [s for s in all_stages if s.stage_id != stage_id]

    breadcrumb = []
    for ancestor_id in stage.lineage_path:
        ancestor = await stage_service.get_stage(ancestor_id)
        if ancestor:
            breadcrumb.append(ancestor)

    return templates.TemplateResponse(
        "stage_detail.html",
        {
            "request": request,
            "stage": stage,
            "form_types": form_types,
            "children": children,
            "breadcrumb": breadcrumb,
            "all_stages": all_stages_for_move,
            "current_user": user,
            "current_user_roles": roles,
        },
    )


# ---------------------------------------------------------------------------
# Form builder
# ---------------------------------------------------------------------------

@router.get("/form-builder/new/{stage_id}", response_class=HTMLResponse)
async def new_form_builder(
    request: Request, stage_id: str, db: AsyncSession = Depends(get_db)
):
    user, roles = await _require_auth(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    stage_service = StageService(db)
    stage = await stage_service.get_stage(stage_id)
    if not stage:
        return HTMLResponse("Stage not found", status_code=404)

    return templates.TemplateResponse(
        "form_builder.html",
        {
            "request": request,
            "form_type": None,
            "stage": stage,
            "current_user": user,
            "current_user_roles": roles,
        },
    )


@router.get("/form-builder/{form_type_id}", response_class=HTMLResponse)
async def form_builder(
    request: Request, form_type_id: str, db: AsyncSession = Depends(get_db)
):
    user, roles = await _require_auth(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    ft_service = FormTypeService(db)
    form_type = await ft_service.get_form_type_with_schema(form_type_id)
    if not form_type:
        return HTMLResponse("Form type not found", status_code=404)

    stage_service = StageService(db)
    stage = await stage_service.get_stage(form_type.stage_id)

    return templates.TemplateResponse(
        "form_builder.html",
        {
            "request": request,
            "form_type": form_type,
            "stage": stage,
            "current_user": user,
            "current_user_roles": roles,
        },
    )


# ---------------------------------------------------------------------------
# Form views
# ---------------------------------------------------------------------------

@router.get("/forms/{form_type_id}/new", response_class=HTMLResponse)
async def new_form_view(
    request: Request, form_type_id: str, db: AsyncSession = Depends(get_db)
):
    user, roles = await _require_auth(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    ft_service = FormTypeService(db)
    form_type = await ft_service.get_form_type_with_schema(form_type_id)
    if not form_type:
        return HTMLResponse("Form type not found", status_code=404)
    stage_service = StageService(db)
    stage = await stage_service.get_stage(form_type.stage_id)
    return templates.TemplateResponse(
        "form_view.html",
        {
            "request": request,
            "form_type": form_type,
            "stage": stage,
            "record": None,
            "current_user": user,
            "current_user_roles": roles,
        },
    )


@router.get("/forms/{form_type_id}/{record_id}", response_class=HTMLResponse)
async def edit_form_view(
    request: Request,
    form_type_id: str,
    record_id: str,
    db: AsyncSession = Depends(get_db),
):
    user, roles = await _require_auth(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

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
    return templates.TemplateResponse(
        "form_view.html",
        {
            "request": request,
            "form_type": form_type,
            "stage": stage,
            "record": record,
            "current_user": user,
            "current_user_roles": roles,
        },
    )


@router.get("/forms/{form_type_id}", response_class=HTMLResponse)
async def list_form_view(
    request: Request, form_type_id: str, db: AsyncSession = Depends(get_db)
):
    user, roles = await _require_auth(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    ft_service = FormTypeService(db)
    form_type = await ft_service.get_form_type_with_schema(form_type_id)
    if not form_type:
        return HTMLResponse("Form type not found", status_code=404)
    svc = FormRecordService(db)
    items, total = await svc.list_by_form_type(form_type_id, limit=100)
    stage_service = StageService(db)
    stage = await stage_service.get_stage(form_type.stage_id)
    return templates.TemplateResponse(
        "form_list.html",
        {
            "request": request,
            "form_type": form_type,
            "stage": stage,
            "records": items,
            "total": total,
            "current_user": user,
            "current_user_roles": roles,
        },
    )


# ---------------------------------------------------------------------------
# Permissions & Roles
# ---------------------------------------------------------------------------

@router.get("/permissions", response_class=HTMLResponse)
async def permissions_page(request: Request, db: AsyncSession = Depends(get_db)):
    user, roles = await _require_auth(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not user.is_superadmin:
        return HTMLResponse("Access denied — superadmin only", status_code=403)

    stage_service = StageService(db)
    ft_service = FormTypeService(db)

    stages = await stage_service.get_all_stages(limit=500)
    form_types = await ft_service.get_all_form_types(limit=500)

    stages_data = [stage.model_dump(mode="json") for stage in stages]
    form_types_data = [ft.model_dump(mode="json") for ft in form_types]

    return templates.TemplateResponse(
        "permissions.html",
        {
            "request": request,
            "stages": stages_data,
            "form_types": form_types_data,
            "current_user": user,
            "current_user_roles": roles,
        },
    )


@router.get("/roles", response_class=HTMLResponse)
async def roles_page(request: Request, db: AsyncSession = Depends(get_db)):
    user, roles = await _require_auth(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not user.is_superadmin:
        return HTMLResponse("Access denied — superadmin only", status_code=403)

    stage_service = StageService(db)
    ft_service = FormTypeService(db)

    stages = await stage_service.get_all_stages(limit=500)
    form_types = await ft_service.get_all_form_types(limit=500)

    return templates.TemplateResponse(
        "roles.html",
        {
            "request": request,
            "stages": stages,
            "form_types": form_types,
            "current_user": user,
            "current_user_roles": roles,
        },
    )


# ---------------------------------------------------------------------------
# User Profile
# ---------------------------------------------------------------------------

@router.get("/profile", response_class=HTMLResponse)
async def profile_page(request: Request, db: AsyncSession = Depends(get_db)):
    user, roles = await _require_auth(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    # Resolve presigned photo URL if photo key is set
    photo_url = None
    if user.profile_photo_url:
        from datetime import timedelta
        from src.app.storage import storage_service
        photo_url = storage_service.generate_presigned_url(
            object_name=user.profile_photo_url,
            expires=timedelta(hours=1),
        )

    return templates.TemplateResponse(
        "profile.html",
        {
            "request": request,
            "current_user": user,
            "current_user_roles": roles,
            "photo_url": photo_url,
        },
    )


# ---------------------------------------------------------------------------
# User Management (superadmin only)
# ---------------------------------------------------------------------------

@router.get("/users", response_class=HTMLResponse)
async def users_page(request: Request, db: AsyncSession = Depends(get_db)):
    user, roles = await _require_auth(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    if not user.is_superadmin:
        return HTMLResponse("Access denied — superadmin only", status_code=403)

    user_service = UserService(db)
    all_users_with_roles = await user_service.list_users(limit=200)

    from src.app.services.permission_service import PermissionService
    perm_service = PermissionService(db)
    all_roles = await perm_service.list_all_roles()

    users_data = [
        {**u.to_dict(), "roles": r}
        for u, r in all_users_with_roles
    ]

    return templates.TemplateResponse(
        "users.html",
        {
            "request": request,
            "current_user": user,
            "current_user_roles": roles,
            "users": users_data,
            "all_roles": all_roles,
        },
    )
