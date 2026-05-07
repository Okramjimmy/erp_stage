from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.auth import get_current_user_optional
from src.app.database import get_db
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
async def create_stage(stage_data: StageCreate, db: AsyncSession = Depends(get_db)):
    """
    Create a new stage.

    - **stage_name**: Name of the stage
    - **parent_stage_id**: Optional parent stage ID for nesting
    - **visibility_scope**: Visibility level (public, private, restricted)
    """
    service = StageService(db)
    try:
        return await service.create_stage(stage_data, created_by="system")
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
        return await service.get_stage_tree(
            root_stage_id=root_stage_id, max_depth=max_depth, user_id=user_id
        )
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


@router.get("/{stage_id}", response_model=StageResponse)
async def get_stage(stage_id: str, db: AsyncSession = Depends(get_db)):
    """Get a specific stage by ID."""
    service = StageService(db)
    stage = await service.get_stage(stage_id)
    if not stage:
        raise HTTPException(status_code=404, detail=f"Stage {stage_id} not found")
    return stage


@router.put("/{stage_id}", response_model=StageResponse)
async def update_stage(
    stage_id: str, stage_data: StageUpdate, db: AsyncSession = Depends(get_db)
):
    """Update a stage."""
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
    stage_id: str, move_request: StageMoveRequest, db: AsyncSession = Depends(get_db)
):
    """
    Move a stage to a new parent.

    Updates all descendants recursively.
    """
    service = StageService(db)
    try:
        return await service.move_stage(
            stage_id=stage_id,
            target_parent_id=move_request.target_parent_id,
            user_id="system",
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{stage_id}")
async def delete_stage(
    stage_id: str,
    recursive: bool = Query(True, description="Delete recursively (default: true)"),
    preview: bool = Query(False, description="Return preview of what would be deleted without actually deleting"),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a stage and all its descendants recursively.

    By default, deleting a stage will delete ALL its children (cascade delete).
    Set recursive=false to only delete the single stage (use with caution).

    Set preview=true to see what would be deleted without actually deleting it.
    This returns a detailed list of stages and form types that would be affected.
    """
    service = StageService(db)
    try:
        result = await service.delete_stage(stage_id, recursive=recursive, preview=preview)
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
