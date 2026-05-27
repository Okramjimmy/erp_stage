from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.auth import get_current_user, get_current_user_optional
from src.app.database import get_db
from src.app.models.user import User
from src.app.schemas.stage import (
    StageCreate,
    StageMoveRequest,
    StageMoveResponse,
    StageResponse,
    StageTreeNode,
    StageUpdate,
)
from src.app.services.stage_service import StageService

router = APIRouter(prefix="/stages", tags=["Stages"])


@router.post("", response_model=StageResponse, status_code=201)
async def create_stage(
    stage_data: StageCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new stage.

    The created_by field is automatically set from the authenticated user.

    - **stage_name**: Name of the stage
    - **parent_stage_id**: Optional parent stage ID for nesting
    - **visibility_scope**: Visibility level (public, private, restricted)
    """
    from src.app.services.permission_service import PermissionService
    perm_service = PermissionService(db)
    
    if stage_data.parent_stage_id:
        has_perm = await perm_service.check_stage_permission(current_user.user_id, stage_data.parent_stage_id, "can_create")
        if not has_perm:
            raise HTTPException(status_code=403, detail="Permission denied to create a child stage here.")
    else:
        if not await perm_service.is_superadmin(current_user.user_id):
            raise HTTPException(status_code=403, detail="Only superadmins can create root stages.")

    service = StageService(db)
    try:
        return await service.create_stage(stage_data, created_by=current_user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("", response_model=List[StageResponse])
async def list_stages(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """List all stages with pagination."""
    service = StageService(db)
    return await service.get_all_stages(skip=skip, limit=limit)


@router.get("/tree", response_model=List[StageTreeNode])
async def get_stage_tree(
    root_stage_id: Optional[str] = Query(
        None, description="Root stage ID to start from"
    ),
    max_depth: Optional[int] = Query(
        None, ge=0, description="Maximum depth to traverse"
    ),
    user_id: Optional[str] = Query(
        None, description="User ID to filter by stage visibility"
    ),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user_optional),
):
    """
    Get hierarchical stage tree.

    - **root_stage_id**: Optional root stage ID to get subtree
    - **max_depth**: Optional maximum depth to limit tree traversal
    - **user_id**: Optional user ID to filter by stage visibility (only stages visible to this user)
    """
    if not user_id and current_user:
        user_id = current_user.user_id

    service = StageService(db)
    try:
        tree = await service.get_stage_tree(
            root_stage_id=root_stage_id, max_depth=max_depth, user_id=user_id
        )
        if current_user:
            from src.app.services.permission_service import PermissionService
            perm_service = PermissionService(db)
            user_perms = await perm_service.get_user_permissions(
                current_user.user_id
            )

            def populate_tree_perms(node):
                node.allowed_permissions = user_perms["stages"].get(node.stage_id, {
                    "view": False,
                    "create": False,
                    "edit": False,
                    "delete": False,
                    "manage_permissions": False,
                    "submit": False
                })
                for ft in node.form_types:
                    ft.allowed_permissions = user_perms["form_types"].get(ft.form_type_id, {
                        "view": False,
                        "create": False,
                        "edit": False,
                        "delete": False,
                        "submit": False,
                        "manage_permissions": False
                    })
                for child in node.children:
                    populate_tree_perms(child)

            for node in tree:
                populate_tree_perms(node)

        return tree
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/search", response_model=List[StageResponse])
async def search_stages(
    q: str = Query(..., min_length=1, description="Search query"),
    limit: int = Query(50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """Search stages by name."""
    service = StageService(db)
    return await service.search_stages(query=q, limit=limit)


@router.post("/upload")
async def upload_stage_file(
    stage_id: str = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload a file for a specific stage, stored in the stage's directory in MinIO.
    Max file size: 50MB.
    """
    # 1. Enforce max file size of 50MB
    MAX_SIZE = 50 * 1024 * 1024
    if file.size and file.size > MAX_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds the maximum limit of 50MB")
    
    file_content = await file.read()
    if len(file_content) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds the maximum limit of 50MB")

    # Extract filename from uploaded file
    filename = file.filename
    if not filename:
        raise HTTPException(status_code=400, detail="Uploaded file must have a filename")

    # 2. Check if stage exists
    service = StageService(db)
    stage = await service.get_stage(stage_id)
    if not stage:
        raise HTTPException(status_code=404, detail=f"Stage {stage_id} not found")

    # 3. Upload to MinIO
    from src.app.storage import storage_service
    object_name = f"{stage_id}/uploads/{filename}"
    success = storage_service.upload_file(
        file_data=file_content,
        object_name=object_name,
        content_type=file.content_type or "application/octet-stream"
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to upload file to storage")

    return {
        "status": "success",
        "message": "File uploaded successfully",
        "stage_id": stage_id,
        "filename": filename,
        "object_name": object_name
    }


@router.get("/download")
async def download_stage_file(
    stage_id: str = Query(...),
    filename: str = Query(...),
    request: Request = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Generate a presigned URL to download a file associated with a stage.
    """
    # 1. Check if stage exists
    service = StageService(db)
    stage = await service.get_stage(stage_id)
    if not stage:
        raise HTTPException(status_code=404, detail=f"Stage {stage_id} not found")

    # 2. Check if file exists in the stage folder
    from src.app.storage import storage_service
    object_name = f"{stage_id}/uploads/{filename}"
    
    files = storage_service.list_files(prefix=f"{stage_id}/uploads/")
    if object_name not in files:
        raise HTTPException(status_code=404, detail=f"File {filename} not found in stage {stage_id}")

    # 3. Generate presigned URL
    from datetime import timedelta
    url = storage_service.generate_presigned_url(
        object_name=object_name,
        expires=timedelta(hours=1)
    )

    if not url:
        raise HTTPException(status_code=500, detail="Failed to generate presigned URL")

    if request and request.url.hostname:
        from urllib.parse import urlparse, urlunparse
        parsed_url = urlparse(url)
        port = parsed_url.port
        netloc = f"{request.url.hostname}:{port}" if port else request.url.hostname
        url = urlunparse(parsed_url._replace(netloc=netloc))

    return {
        "url": url
    }


@router.get("/{stage_id}", response_model=StageResponse)
async def get_stage(
    stage_id: str,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(get_current_user_optional)
):
    """Get a specific stage by ID."""
    service = StageService(db)
    stage = await service.get_stage(stage_id)
    if not stage:
        raise HTTPException(status_code=404, detail=f"Stage {stage_id} not found")

    response_data = StageResponse.model_validate(stage)
    if current_user:
        from src.app.services.permission_service import PermissionService
        perm_service = PermissionService(db)
        user_perms = await perm_service.get_user_permissions(
            current_user.user_id
        )
        response_data.allowed_permissions = user_perms["stages"].get(stage_id, {
            "view": False,
            "create": False,
            "edit": False,
            "delete": False,
            "manage_permissions": False,
            "submit": False
        })
    return response_data


@router.put("/{stage_id}", response_model=StageResponse)
async def update_stage(
    stage_id: str, 
    stage_data: StageUpdate, 
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Update a stage."""
    from src.app.services.permission_service import PermissionService
    perm_service = PermissionService(db)
    
    has_perm = await perm_service.check_stage_permission(current_user.user_id, stage_id, "can_edit")
    if not has_perm:
        raise HTTPException(status_code=403, detail="Permission denied to edit this stage.")

    service = StageService(db)
    stage = await service.get_stage(stage_id)
    if not stage:
        raise HTTPException(status_code=404, detail=f"Stage {stage_id} not found")
    try:
        return await service.update_stage(stage_id, stage_data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{stage_id}/move", response_model=StageMoveResponse)
async def move_stage(
    stage_id: str,
    move_request: StageMoveRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Move a stage to a new parent.

    Updates all descendants recursively. The user_id is automatically set from the authenticated user.
    """
    from src.app.services.permission_service import PermissionService
    perm_service = PermissionService(db)
    has_edit = await perm_service.check_stage_permission(current_user.user_id, stage_id, "can_edit")
    if not has_edit:
        raise HTTPException(status_code=403, detail="Permission denied to move this stage.")
        
    if move_request.target_parent_id:
        has_create = await perm_service.check_stage_permission(current_user.user_id, move_request.target_parent_id, "can_create")
        if not has_create:
            raise HTTPException(status_code=403, detail="Permission denied to create a child in the target stage.")
    else:
        if not await perm_service.is_superadmin(current_user.user_id):
            raise HTTPException(status_code=403, detail="Only superadmins can move a stage to the root level.")

    service = StageService(db)
    try:
        return await service.move_stage(
            stage_id=stage_id,
            target_parent_id=move_request.target_parent_id,
            user_id=current_user.user_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{stage_id}")
async def delete_stage(
    stage_id: str,
    recursive: bool = Query(True, description="Delete recursively (default: true)"),
    preview: bool = Query(False, description="Return preview of what would be deleted without actually deleting"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a stage and all its descendants recursively.

    By default, deleting a stage will delete ALL its children (cascade delete).
    Set recursive=false to only delete the single stage (use with caution).

    Set preview=true to see what would be deleted without actually deleting it.
    This returns a detailed list of stages and form types that would be affected.
    """
    from src.app.services.permission_service import PermissionService
    permission_service = PermissionService(db)
    has_permission = await permission_service.check_stage_permission(
        user_id=current_user.user_id,
        stage_id=stage_id,
        permission_type="can_delete"
    )
    if not has_permission:
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to delete this stage"
        )

    service = StageService(db)
    try:
        result = await service.delete_stage(stage_id, recursive=recursive, preview=preview)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{stage_id}/permissions")
async def get_stage_permissions(
    stage_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Get resolved permissions of the current user for this stage and its linked form types.
    """
    from src.app.services.permission_service import PermissionService
    from src.app.services.form_type_service import FormTypeService

    perm_service = PermissionService(db)
    ft_service = FormTypeService(db)

    # 1. Resolve permissions for the user
    user_perms = await perm_service.get_user_permissions(
        current_user.user_id
    )

    # 2. Get this stage's permissions
    stage_perms = user_perms["stages"].get(stage_id, {
        "view": False,
        "create": False,
        "edit": False,
        "delete": False,
        "manage_permissions": False
    })

    # 3. Get form types linked to this stage
    form_types = await ft_service.get_form_types_by_stage(stage_id)
    form_type_ids = [ft.form_type_id for ft in form_types]

    form_perms = {}
    for ft_id in form_type_ids:
        form_perms[ft_id] = user_perms["form_types"].get(ft_id, {
            "view": False,
            "create": False,
            "edit": False,
            "delete": False,
            "submit": False,
            "manage_permissions": False
        })

    return {
        "stage_id": stage_id,
        "permissions": {
            "stage": stage_perms,
            "form_types": form_perms
        }
    }
