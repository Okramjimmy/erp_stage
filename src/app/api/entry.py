"""UI routes — renders Jinja2 HTML templates."""

from starlette.status import HTTP_404_NOT_FOUND
from fastapi import APIRouter, Depends, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from src.app.core.auth import get_current_user, get_current_user_optional, _require_auth
from src.app.database import get_db
from src.app.services.form_record_service import FormRecordService
from src.app.services.form_type_service import FormTypeService
from src.app.services.stage_service import StageService
from src.app.services.user_service import UserService

router = APIRouter(prefix="/entry",tags=["ENTRY"])


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@router.get("/")
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    user, roles = await _require_auth(request, db)
    if not user:
        raise HTTP_404_NOT_FOUND("You are not authorized to access this page")

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

    return {
        "tree": tree,
        "stages": stages,
        "form_types": form_types,
        "total_stages": len(stages),
        "total_forms": len(form_types),
        "current_user": user,
        "current_user_roles": roles,
        "user_permissions": user_permissions,
    }


# ---------------------------------------------------------------------------
# Stage detail
# ---------------------------------------------------------------------------

@router.get("/stages/{stage_id}")
async def stage_detail(
    request: Request, stage_id: str, db: AsyncSession = Depends(get_db)
):
    user, roles = await _require_auth(request, db)
    if not user:
        raise HTTP_404_NOT_FOUND("You are not authorized to access this page")

    stage_service = StageService(db)
    stage = await stage_service.get_stage(stage_id)
    if not stage:
        raise HTTP_404_NOT_FOUND("Stage not found")

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

    return {
        "stage": stage,
        "form_types": form_types,
        "children": children,
        "breadcrumb": breadcrumb,
        "all_stages": all_stages_for_move,
        "current_user": user,
        "current_user_roles": roles,
        "user_permissions": user_permissions,
    }


# ---------------------------------------------------------------------------
# Form builder
# ---------------------------------------------------------------------------

@router.get("/form-builder/new/{stage_id}")
async def new_form_builder(
    request: Request, stage_id: str, db: AsyncSession = Depends(get_db)
):
    user, roles = await _require_auth(request, db)
    if not user:
        raise HTTP_404_NOT_FOUND("You are not authorized to access this page")

    stage = None
    if stage_id != "standalone":
        stage_service = StageService(db)
        stage = await stage_service.get_stage(stage_id)
        if not stage:
            raise HTTP_404_NOT_FOUND("Stage not found")

    return {
        "form_type": None,
        "stage": stage,
        "current_user": user,
        "current_user_roles": roles,
    }


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


@router.get("/form-builder/{form_type_id}")
async def form_builder(
    request: Request, form_type_id: str, db: AsyncSession = Depends(get_db)
):
    user, roles = await _require_auth(request, db)
    if not user:
        raise HTTP_404_NOT_FOUND("You are not authorized to access this page")

    ft_service = FormTypeService(db)
    form_type = await ft_service.get_form_type_with_schema(form_type_id)
    if not form_type:
        raise HTTP_404_NOT_FOUND("Form type not found")

    stage = await _get_stage_for_form_type(db, form_type_id)
    from src.app.services.permission_service import PermissionService
    perm_service = PermissionService(db)
    user_permissions = await perm_service.get_user_permissions(user.user_id)

    return {
        "form_type": form_type,
        "stage": stage,
        "current_user": user,
        "current_user_roles": roles,
        "user_permissions": user_permissions,
    }


@router.get("/workflow-builder/{form_type_id}")
async def workflow_builder(
    request: Request, form_type_id: str, db: AsyncSession = Depends(get_db)
):
    user, roles = await _require_auth(request, db)
    if not user:
        raise HTTP_404_NOT_FOUND("You are not authorized to access this page")

    ft_service = FormTypeService(db)
    form_type = await ft_service.get_form_type_with_schema(form_type_id)
    if not form_type:
        raise HTTP_404_NOT_FOUND("Form type not found")

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

    return {
        "form_type": form_type,
        "stage": stage,
        "current_user": user,
        "current_user_roles": roles,
        "user_permissions": user_permissions,
        "can_edit": can_edit,
        "all_roles": all_roles_raw,
    }

# ---------------------------------------------------------------------------
# Form views
# ---------------------------------------------------------------------------

@router.get("/forms/{form_type_id}/new")
async def new_form_view(
    request: Request, form_type_id: str, db: AsyncSession = Depends(get_db)
):
    user, roles = await _require_auth(request, db)
    if not user:
        raise HTTP_404_NOT_FOUND("You are not authorized to access this page")

    ft_service = FormTypeService(db)
    form_type = await ft_service.get_form_type_with_schema(form_type_id)
    if not form_type:
        raise HTTP_404_NOT_FOUND("Form type not found")
    stage = await _get_stage_for_form_type(db, form_type_id)
    from src.app.services.permission_service import PermissionService
    perm_service = PermissionService(db)
    user_permissions = await perm_service.get_user_permissions(user.user_id)
    return {
        "form_type": form_type,
        "stage": stage,
        "record": None,
        "current_user": user,
        "current_user_roles": roles,
        "user_permissions": user_permissions,
    }


@router.get("/forms/{form_type_id}/{record_id}")
async def edit_form_view(
    request: Request,
    form_type_id: str,
    record_id: str,
    db: AsyncSession = Depends(get_db),
):
    user, roles = await _require_auth(request, db)
    if not user:
        raise HTTP_404_NOT_FOUND("You are not authorized to access this page")

    ft_service = FormTypeService(db)
    form_type = await ft_service.get_form_type_with_schema(form_type_id)
    if not form_type:
        raise HTTP_404_NOT_FOUND("Form type not found")
    svc = FormRecordService(db)
    record = await svc.get(record_id)
    if not record:
        raise HTTP_404_NOT_FOUND("Record not found")
    stage = await _get_stage_for_form_type(db, form_type_id)
    from src.app.services.permission_service import PermissionService
    perm_service = PermissionService(db)
    user_permissions = await perm_service.get_user_permissions(user.user_id)
    return {
        "form_type": form_type,
        "stage": stage,
        "record": record,
        "current_user": user,
        "current_user_roles": roles,
        "user_permissions": user_permissions,
    }


@router.get("/forms/{form_type_id}")
async def list_form_view(
    request: Request, form_type_id: str, db: AsyncSession = Depends(get_db)
):
    user, roles = await _require_auth(request, db)
    if not user:
        raise HTTP_404_NOT_FOUND("You are not authorized to access this page")

    ft_service = FormTypeService(db)
    form_type = await ft_service.get_form_type_with_schema(form_type_id)
    if not form_type:
        raise HTTP_404_NOT_FOUND("Form type not found")
    svc = FormRecordService(db)
    items, total = await svc.list_by_form_type(form_type_id, limit=100)
    stage = await _get_stage_for_form_type(db, form_type_id)
    from src.app.services.permission_service import PermissionService
    perm_service = PermissionService(db)
    user_permissions = await perm_service.get_user_permissions(user.user_id)
    return {
        "form_type": form_type,
        "stage": stage,
        "records": items,
        "total": total,
        "current_user": user,
        "current_user_roles": roles,
        "user_permissions": user_permissions,
    }

@router.get("/forms")
async def forms_page(request: Request, db: AsyncSession = Depends(get_db)):
    user, roles = await _require_auth(request, db)
    if not user:
        raise HTTP_404_NOT_FOUND("You are not authorized to access this page")
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
        
    return {
        "current_user": user,
        "current_user_roles": roles,
        "form_types": form_types,
        "user_permissions": user_permissions,
    }


# ---------------------------------------------------------------------------
# Permissions & Roles
# ---------------------------------------------------------------------------

@router.get("/permissions")
async def permissions_page(request: Request, db: AsyncSession = Depends(get_db)):
    user, roles = await _require_auth(request, db)
    if not user:
        raise HTTP_404_NOT_FOUND("You are not authorized to access this page")
    is_superadmin = "superadmin" in (roles or [])
    if not is_superadmin:
        raise HTTP_404_NOT_FOUND("Access denied — superadmin only")

    stage_service = StageService(db)
    ft_service = FormTypeService(db)

    stages = await stage_service.get_all_stages(limit=500)
    form_types = await ft_service.get_all_form_types(limit=500)

    stages_data = [stage.model_dump(mode="json") for stage in stages]
    form_types_data = [ft.model_dump(mode="json") for ft in form_types]

    return {
        "stages": stages_data,
        "form_types": form_types_data,
        "current_user": user,
        "current_user_roles": roles,
    }


@router.get("/roles")
async def roles_page(request: Request, db: AsyncSession = Depends(get_db)):
    user, roles = await _require_auth(request, db)
    if not user:
        raise HTTP_404_NOT_FOUND("You are not authorized to access this page")
    is_superadmin = "superadmin" in (roles or [])
    if not is_superadmin:
        raise HTTP_404_NOT_FOUND("Access denied — superadmin only")

    stage_service = StageService(db)
    ft_service = FormTypeService(db)

    stages = await stage_service.get_all_stages(limit=500)
    form_types = await ft_service.get_all_form_types(limit=500)

    return {
        "stages": stages,
        "form_types": form_types,
        "current_user": user,
        "current_user_roles": roles,
    }


# ---------------------------------------------------------------------------
# User Profile
# ---------------------------------------------------------------------------

@router.get("/profile")
async def profile_page(request: Request, db: AsyncSession = Depends(get_db)):
    user, roles = await _require_auth(request, db)
    if not user:
        raise HTTP_404_NOT_FOUND("You are not authorized to access this page")

    # Resolve presigned photo URL if photo key is set
    photo_url = None
    if user.profile_photo_url:
        from datetime import timedelta
        from src.app.storage import storage_service
        photo_url = storage_service.generate_presigned_url(
            object_name=user.profile_photo_url,
            expires=timedelta(hours=1),
        )

    return {
        "current_user": user,
        "current_user_roles": roles,
        "photo_url": photo_url,
    }


# ---------------------------------------------------------------------------
# User Management (superadmin only)
# ---------------------------------------------------------------------------

@router.get("/users")
async def users_page(request: Request, db: AsyncSession = Depends(get_db)):
    user, roles = await _require_auth(request, db)
    if not user:
        raise HTTP_404_NOT_FOUND("You are not authorized to access this page")
    is_superadmin = "superadmin" in (roles or [])
    if not is_superadmin:
        raise HTTP_404_NOT_FOUND("Access denied — superadmin only")

    user_service = UserService(db)
    all_users_with_roles = await user_service.list_users(limit=200)

    from src.app.services.permission_service import PermissionService
    perm_service = PermissionService(db)
    all_roles = await perm_service.list_all_roles()

    users_data = [
        {**u.to_dict(), "roles": r}
        for u, r in all_users_with_roles
    ]

    return {
        "current_user": user,
        "current_user_roles": roles,
        "users": users_data,
        "all_roles": all_roles,
    }


# ---------------------------------------------------------------------------
# Submissions Management (superadmin and manager only)
# ---------------------------------------------------------------------------

@router.get("/submissions")
async def submissions_page(
    request: Request,
    created_by: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db)
):
    user, roles = await _require_auth(request, db)
    if not user:
        raise HTTP_404_NOT_FOUND("You are not authorized to access this page")

    is_superadmin = "superadmin" in (roles or [])
    is_manager = "manager" in (roles or [])

    if not is_superadmin and not is_manager:
        raise HTTP_404_NOT_FOUND("Access denied — superadmins and managers only")

    from src.app.models.form_record import FormRecord
    from src.app.models.form_type import FormType
    from src.app.models.stage import Stage
    from src.app.models.user import User
    from src.app.services.permission_service import PermissionService
    from sqlalchemy import select, and_, or_

    perm_service = PermissionService(db)
    user_perms = await perm_service.get_user_permissions(user.user_id)
    
    # Identify which form types are viewable by this user
    if is_superadmin:
        # Superadmin can view all form types
        fts_res = await db.execute(select(FormType).order_by(FormType.form_name))
        all_accessible_fts = fts_res.scalars().all()
        allowed_form_type_ids = [ft.form_type_id for ft in all_accessible_fts]
    else:
        # Manager can view form types they have access to
        allowed_form_type_ids = [
            ft_id for ft_id, perms in user_perms.get("form_types", {}).items()
            if perms.get("view")
        ]
        if allowed_form_type_ids:
            fts_res = await db.execute(
                select(FormType)
                .where(FormType.form_type_id.in_(allowed_form_type_ids))
                .order_by(FormType.form_name)
            )
            all_accessible_fts = fts_res.scalars().all()
        else:
            all_accessible_fts = []

    # Get list of all stages for filter dropdown
    stages_res = await db.execute(select(Stage).order_by(Stage.stage_name))
    all_stages = stages_res.scalars().all()

    # Query latest records
    stmt = (
        select(FormRecord, FormType.form_name, Stage.stage_name, User.full_name.label("creator_name"))
        .join(FormType, FormRecord.form_type_id == FormType.form_type_id)
        .outerjoin(Stage, FormRecord.stage_id == Stage.stage_id)
        .outerjoin(User, FormRecord.created_by == User.user_id)
    )

    # Restrict to accessible form types
    stmt = stmt.where(FormRecord.form_type_id.in_(allowed_form_type_ids))

    # Apply backend filter only if created_by is queried
    if created_by:
        stmt = stmt.where(
            or_(
                User.full_name.ilike(f"%{created_by}%"),
                User.username.ilike(f"%{created_by}%"),
                FormRecord.created_by.ilike(f"%{created_by}%")
            )
        )

    # Always sort by newest on the database query by default
    stmt = stmt.order_by(FormRecord.created_at.desc())

    # Limit to 100 submissions
    stmt = stmt.limit(100)
    
    res = await db.execute(stmt)
    records_rows = res.all()

    records_data = []
    for row in records_rows:
        record_obj = row[0]
        form_name = row[1]
        stage_name = row[2]
        creator_name = row[3]
        records_data.append({
            "record_id": record_obj.record_id,
            "docname": record_obj.docname,
            "form_type_id": record_obj.form_type_id,
            "form_name": form_name,
            "stage_id": record_obj.stage_id,
            "stage_name": stage_name or "Global",
            "status": record_obj.status,
            "created_by": record_obj.created_by,
            "creator_name": creator_name or record_obj.created_by or "System",
            "created_at_iso": record_obj.created_at.isoformat() if record_obj.created_at else "",
            "created_at_formatted": record_obj.created_at.strftime('%d %b %Y, %H:%M') if record_obj.created_at else "",
        })

    return {
        "current_user": user,
        "current_user_roles": roles,
        "records": records_data,
        "stages": [s.to_dict() if hasattr(s, "to_dict") else {"stage_id": s.stage_id, "stage_name": s.stage_name} for s in all_stages],
        "form_types": [f.to_dict() if hasattr(f, "to_dict") else {"form_type_id": f.form_type_id, "form_name": f.form_name} for f in all_accessible_fts],
    }
