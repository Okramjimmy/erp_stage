"""Users API endpoints — CRUD, photo upload, role management."""

import io
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.auth import get_current_user, require_superadmin
from src.app.database import get_db
from src.app.models.user import User
from src.app.schemas.user import UserCreate, UserListItem, UserPasswordChange, UserResponse, UserUpdate
from src.app.services.user_service import UserService
from src.app.storage import storage_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/users", tags=["Users"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_minio_photo_key(user_id: str, department: Optional[str], filename: str) -> str:
    """
    Construct the MinIO object key for a user photo.
    Pattern: users/{user_id}_{department}/photo.{ext}
    Falls back to "general" if department is not set.
    """
    dept = (department or "general").lower().replace(" ", "_")
    folder = f"users/{user_id}_{dept}"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    return f"{folder}/photo.{ext}"


def _user_to_response(user: User, roles: List[str]) -> UserResponse:
    return UserResponse(**user.to_dict(), roles=roles)


def _user_to_list_item(user: User, roles: List[str]) -> UserListItem:
    return UserListItem(**user.to_dict(), roles=roles)


# ---------------------------------------------------------------------------
# List & Create (superadmin only)
# ---------------------------------------------------------------------------

@router.get("", response_model=List[UserListItem])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all users with their assigned roles."""
    service = UserService(db)
    pairs = await service.list_users(skip=skip, limit=limit)

    if current_user.is_superadmin:
        return [_user_to_list_item(u, r) for u, r in pairs]

    # Non-superadmins can only see users who are not superadmins
    return [
        _user_to_list_item(u, r)
        for u, r in pairs
        if not u.is_superadmin and "superadmin" not in (r or [])
    ]


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(require_superadmin),
):
    """Create a new user (superadmin only). The created_by field is automatically set from the admin user."""
    service = UserService(db)
    try:
        user = await service.create_user(data, created_by=admin.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return UserResponse(**user.to_dict(), roles=[])


# ---------------------------------------------------------------------------
# Individual user
# ---------------------------------------------------------------------------

@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a user by ID. Users can only fetch themselves; superadmins can fetch any."""
    if not current_user.is_superadmin and current_user.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    service = UserService(db)
    result = await service.get_user_with_roles(user_id)
    if not result:
        raise HTTPException(status_code=404, detail="User not found")
    user, roles = result
    return _user_to_response(user, roles)


@router.put("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: str,
    data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update profile fields. Self or superadmin only."""
    if not current_user.is_superadmin and current_user.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")
    service = UserService(db)
    try:
        user = await service.update_user(user_id, data)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    roles = await service.get_user_roles(user.user_id)
    return _user_to_response(user, roles)


@router.put("/{user_id}/password", status_code=204)
async def change_password(
    user_id: str,
    data: UserPasswordChange,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Change a user's own password. Verifies current password first."""
    if current_user.user_id != user_id:
        raise HTTPException(status_code=403, detail="You can only change your own password")
    if data.new_password != data.confirm_password:
        raise HTTPException(status_code=400, detail="New passwords do not match")
    service = UserService(db)
    try:
        await service.change_password(user_id, data.current_password, data.new_password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/{user_id}/status", response_model=UserResponse)
async def set_user_status(
    user_id: str,
    is_active: bool = Query(...),
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_superadmin),
):
    """Activate or deactivate a user (superadmin only)."""
    service = UserService(db)
    try:
        user = await service.set_active(user_id, is_active)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    roles = await service.get_user_roles(user.user_id)
    return _user_to_response(user, roles)


# ---------------------------------------------------------------------------
# Photo upload / retrieve
# ---------------------------------------------------------------------------

@router.post("/{user_id}/photo", response_model=UserResponse)
async def upload_photo(
    user_id: str,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Upload a profile photo to MinIO.
    Stored under key: users/{user_id}_{department}/photo.{ext}
    Sets users.profile_photo_url to this key.
    """
    if not current_user.is_superadmin and current_user.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied")

    service = UserService(db)
    user = await service.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Validate content type
    allowed = {"image/jpeg", "image/jpg", "image/png", "image/gif", "image/webp"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=400, detail="Only JPEG, JPG, PNG, GIF, or WebP images are allowed")

    file_bytes = await file.read()
    minio_key = _build_minio_photo_key(user_id, user.department, file.filename)
    logger.info(f"Uploading photo for user {user_id} to MinIO key: {minio_key}")
    logger.info(f"File bytes: {len(file_bytes)}")
    logger.info(f"Content type: {file.content_type}")

    success = storage_service.upload_file(
        file_data=file_bytes,
        object_name=minio_key,
        content_type=file.content_type,
    )
    if not success:
        raise HTTPException(status_code=500, detail="Failed to upload photo to storage")

    user = await service.update_photo_key(user_id, minio_key)
    roles = await service.get_user_roles(user.user_id)
    return _user_to_response(user, roles)


@router.get("/{user_id}/photo")
async def get_photo_url(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """
    Returns a 1-hour presigned MinIO URL for the user's profile photo.
    Use this URL as <img src="..."> on the profile page.
    """
    from datetime import timedelta

    service = UserService(db)
    user = await service.get_by_id(user_id)
    if not user or not user.profile_photo_url:
        raise HTTPException(status_code=404, detail="No photo set for this user")

    url = storage_service.generate_presigned_url(
        object_name=user.profile_photo_url,
        expires=timedelta(hours=1),
    )
    if not url:
        raise HTTPException(status_code=500, detail="Failed to generate photo URL")

    return {"url": url, "key": user.profile_photo_url}


# ---------------------------------------------------------------------------
# Role management
# ---------------------------------------------------------------------------

@router.get("/{user_id}/roles")
async def get_user_roles(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_user),
):
    """Return all roles assigned to a user."""
    service = UserService(db)
    roles = await service.get_user_roles(user_id)
    return {"user_id": user_id, "roles": roles}


@router.post("/{user_id}/roles", status_code=200)
async def assign_roles(
    user_id: str,
    role_names: List[str],
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_superadmin),
):
    """
    Assign one or more roles to a user (idempotent).
    Body: list of role name strings e.g. ["manager", "viewer"]
    """
    service = UserService(db)
    user = await service.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    await service.assign_roles(user_id, role_names)
    return {"user_id": user_id, "roles": await service.get_user_roles(user_id)}


@router.delete("/{user_id}/roles/{role_name}", status_code=200)
async def revoke_role(
    user_id: str,
    role_name: str,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_superadmin),
):
    """Revoke a single role from a user."""
    service = UserService(db)
    await service.revoke_role(user_id, role_name)
    return {"user_id": user_id, "revoked": role_name, "remaining": await service.get_user_roles(user_id)}
