"""Groups API endpoints — CRUD operations."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.auth import get_current_user, require_superadmin
from src.app.database import get_db
from src.app.models.user import User
from src.app.schemas.group import GroupCreate, GroupResponse, GroupUpdate
from src.app.services.group_service import GroupService

router = APIRouter(prefix="/groups", tags=["Groups"])


@router.get("", response_model=List[GroupResponse])
async def list_groups(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """List all groups (authenticated users only)."""
    service = GroupService(db)
    return await service.list_groups(skip=skip, limit=limit)


@router.post("", response_model=GroupResponse, status_code=status.HTTP_201_CREATED)
async def create_group(
    data: GroupCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_superadmin),
):
    """Create a new group (superadmin only)."""
    service = GroupService(db)
    try:
        return await service.create(data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.get("/{group_id}", response_model=GroupResponse)
async def get_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """Get group details by ID."""
    service = GroupService(db)
    gp = await service.get_by_id(group_id)
    if not gp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Group not found")
    return gp


@router.put("/{group_id}", response_model=GroupResponse)
async def update_group(
    group_id: str,
    data: GroupUpdate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_superadmin),
):
    """Update group details (superadmin only)."""
    service = GroupService(db)
    try:
        return await service.update(group_id, data)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_group(
    group_id: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_superadmin),
):
    """Delete a group (superadmin only)."""
    service = GroupService(db)
    try:
        await service.delete(group_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
