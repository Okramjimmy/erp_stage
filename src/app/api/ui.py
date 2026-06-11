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
    is_superadmin = "superadmin" in (roles or [])
    visible_stage_ids = set(await perm_service.get_visible_stages(user.user_id))
    
    stages = [s for s in await stage_service.get_all_stages(limit=200) if s.stage_id in visible_stage_ids]
    
    if is_superadmin:
        form_types = await ft_service.get_all_form_types(limit=200)
    else:
        # For regular users, form types are visible if they are linked to a visible stage
        from src.app.models.stage_form_type import StageFormType
        from sqlalchemy import select
        result = await db.execute(
            select(StageFormType.form_type_id)
            .where(StageFormType.stage_id.in_(visible_stage_ids))
        )
        visible_ft_ids = {r[0] for r in result.all()}
        all_fts = await ft_service.get_all_form_types(limit=200)
        form_types = [ft for ft in all_fts if ft.form_type_id in visible_ft_ids]

    user_permissions = await perm_service.get_user_permissions(user.user_id)

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
            "user_permissions": user_permissions,
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

    from src.app.services.permission_service import PermissionService
    perm_service = PermissionService(db)
    user_permissions = await perm_service.get_user_permissions(user.user_id)

    is_superadmin = "superadmin" in (roles or [])
    if not is_superadmin:
        visible_stage_ids = set(await perm_service.get_visible_stages(user.user_id))
        children = [s for s in children if s.stage_id in visible_stage_ids]
        all_stages_for_move = [s for s in all_stages_for_move if s.stage_id in visible_stage_ids]
        
        visible_ft_ids = {ftid for ftid, perms in user_permissions["form_types"].items() if any(perms.values())}
        form_types = [ft for ft in form_types if ft.form_type_id in visible_ft_ids]

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
            "user_permissions": user_permissions,
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

    stage = None
    if stage_id != "standalone":
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


async def _get_stage_for_form_type(db: AsyncSession, form_type_id: str):
    from sqlalchemy import select
    from src.app.models.stage_form_type import StageFormType
    from src.app.services.stage_service import StageService

    # Find the first stage ID this form type is linked to
    stmt = select(StageFormType.stage_id).where(StageFormType.form_type_id == form_type_id)
    result = await db.execute(stmt)
    stage_id = result.scalars().first()
    if stage_id:
        stage_service = StageService(db)
        return await stage_service.get_stage(stage_id)
    return None


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

    stage = await _get_stage_for_form_type(db, form_type_id)
    from src.app.services.permission_service import PermissionService
    perm_service = PermissionService(db)
    user_permissions = await perm_service.get_user_permissions(user.user_id)

    return templates.TemplateResponse(
        "form_builder.html",
        {
            "request": request,
            "form_type": form_type,
            "stage": stage,
            "current_user": user,
            "current_user_roles": roles,
            "user_permissions": user_permissions,
        },
    )


@router.get("/workflow-builder/{form_type_id}", response_class=HTMLResponse)
async def workflow_builder(
    request: Request, form_type_id: str, db: AsyncSession = Depends(get_db)
):
    user, roles = await _require_auth(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    ft_service = FormTypeService(db)
    form_type = await ft_service.get_form_type_with_schema(form_type_id)
    if not form_type:
        return HTMLResponse("Form type not found", status_code=404)

    stage = await _get_stage_for_form_type(db, form_type_id)
    from src.app.services.permission_service import PermissionService
    perm_service = PermissionService(db)
    user_permissions = await perm_service.get_user_permissions(user.user_id)
    
    can_edit = False
    if "superadmin" in (roles or []):
        can_edit = True
    elif user_permissions and form_type_id in user_permissions.form_types:
        can_edit = user_permissions.form_types[form_type_id].edit
        
    # We will fetch all roles to populate the assignee dropdown
    all_roles_raw = await perm_service.list_all_roles()
    # all_roles = [{"role_name": r.role_name} for r in all_roles_raw]

    return templates.TemplateResponse(
        "workflow_builder.html",
        {
            "request": request,
            "form_type": form_type,
            "stage": stage,
            "current_user": user,
            "current_user_roles": roles,
            "user_permissions": user_permissions,
            "can_edit": can_edit,
            "all_roles": all_roles_raw,
        },
    )

# ---------------------------------------------------------------------------
# Form views
# ---------------------------------------------------------------------------

@router.get("/forms/{form_type_id}/new", response_class=HTMLResponse)
async def new_form_view(
    request: Request,
    form_type_id: str,
    stage_id: str | None = None,
    from_forms: bool = False,
    db: AsyncSession = Depends(get_db)
):
    user, roles = await _require_auth(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)

    ft_service = FormTypeService(db)
    form_type = await ft_service.get_form_type_with_schema(form_type_id)
    if not form_type:
        return HTMLResponse("Form type not found", status_code=404)
    
    if from_forms:
        stage = None
    elif stage_id:
        stage_service = StageService(db)
        stage = await stage_service.get_stage(stage_id)
    else:
        stage = await _get_stage_for_form_type(db, form_type_id)

    from src.app.services.permission_service import PermissionService
    perm_service = PermissionService(db)
    user_permissions = await perm_service.get_user_permissions(user.user_id)
    return templates.TemplateResponse(
        "form_view.html",
        {
            "request": request,
            "form_type": form_type,
            "stage": stage,
            "record": None,
            "current_user": user,
            "current_user_roles": roles,
            "user_permissions": user_permissions,
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
    stage = await _get_stage_for_form_type(db, form_type_id)
    from src.app.services.permission_service import PermissionService
    perm_service = PermissionService(db)
    user_permissions = await perm_service.get_user_permissions(user.user_id)
    return templates.TemplateResponse(
        "form_view.html",
        {
            "request": request,
            "form_type": form_type,
            "stage": stage,
            "record": record,
            "current_user": user,
            "current_user_roles": roles,
            "user_permissions": user_permissions,
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
    stage = await _get_stage_for_form_type(db, form_type_id)
    from src.app.services.permission_service import PermissionService
    perm_service = PermissionService(db)
    user_permissions = await perm_service.get_user_permissions(user.user_id)
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
            "user_permissions": user_permissions,
        },
    )

@router.get("/forms", response_class=HTMLResponse)
async def forms_page(request: Request, db: AsyncSession = Depends(get_db)):
    user, roles = await _require_auth(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    from src.app.services.permission_service import PermissionService
    perm_service = PermissionService(db)
    ft_service = FormTypeService(db)
    
    is_superadmin = "superadmin" in (roles or [])
    if is_superadmin:
        form_types = await ft_service.get_all_form_types(limit=500)
    else:
        # Fetch visible form types based on stages
        visible_stage_ids = set(await perm_service.get_visible_stages(user.user_id))
        from src.app.models.stage_form_type import StageFormType
        from sqlalchemy import select
        result = await db.execute(
            select(StageFormType.form_type_id)
            .where(StageFormType.stage_id.in_(visible_stage_ids))
        )
        visible_ft_ids = {r[0] for r in result.all()}
        all_fts = await ft_service.get_all_form_types(limit=500)
        form_types = [ft for ft in all_fts if ft.form_type_id in visible_ft_ids]
        
    user_permissions = await perm_service.get_user_permissions(user.user_id)
        
    return templates.TemplateResponse(
        "forms.html",
        {
            "request": request,
            "current_user": user,
            "current_user_roles": roles,
            "form_types": form_types,
            "user_permissions": user_permissions,
        }
    )


# ---------------------------------------------------------------------------
# Permissions & Roles
# ---------------------------------------------------------------------------

@router.get("/permissions", response_class=HTMLResponse)
async def permissions_page(request: Request, db: AsyncSession = Depends(get_db)):
    user, roles = await _require_auth(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=302)
    is_superadmin = "superadmin" in (roles or [])
    if not is_superadmin:
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
    is_superadmin = "superadmin" in (roles or [])
    if not is_superadmin:
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
    is_superadmin = "superadmin" in (roles or [])
    if not is_superadmin:
        return HTMLResponse("Access denied — superadmin only", status_code=403)

    user_service = UserService(db)
    all_users_with_roles = await user_service.list_users(limit=200)

    from src.app.services.permission_service import PermissionService
    perm_service = PermissionService(db)
    all_roles = await perm_service.list_all_roles()

    from src.app.services.department_service import DepartmentService
    dept_service = DepartmentService(db)
    all_departments = await dept_service.list_departments(limit=50)

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
            "departments": all_departments,
        },
    )
