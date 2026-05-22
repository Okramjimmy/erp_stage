"""Auth dependencies — session helpers and FastAPI dependency providers."""

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.database import get_db

SESSION_KEY = "user_id"


def set_session(request: Request, user_id: str) -> None:
    """Store user_id in the signed session cookie."""
    request.session[SESSION_KEY] = user_id


def clear_session(request: Request) -> None:
    """Remove the user session."""
    request.session.clear()


def get_session_user_id(request: Request) -> str | None:
    """Return the user_id stored in session, or None."""
    return request.session.get(SESSION_KEY)


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    FastAPI dependency that reads the session cookie and returns the User ORM object.
    Raises HTTP 401 if not authenticated.
    """
    from src.app.services.user_service import UserService  # local import to avoid circular

    user_id = get_session_user_id(request)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    service = UserService(db)
    user = await service.get_by_id(user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user


async def get_current_user_optional(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """Like get_current_user but returns None instead of raising 401 — used for UI redirects."""
    from src.app.services.user_service import UserService

    user_id = get_session_user_id(request)
    if not user_id:
        return None
    service = UserService(db)
    user = await service.get_by_id(user_id)
    if not user or not user.is_active:
        return None
    return user


async def _require_auth(request: Request, db: AsyncSession):
    """Return (user, roles) or redirect to /login."""
    from src.app.services.user_service import UserService
    user_id = get_session_user_id(request)
    if not user_id:
        return None, None
    service = UserService(db)
    result = await service.get_user_with_roles(user_id)
    if not result:
        return None, None
    user, roles = result
    if not user.is_active:
        return None, None
    return user, roles


async def require_superadmin(
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """FastAPI dependency that enforces superadmin-only access."""
    from src.app.services.permission_service import PermissionService
    perm_service = PermissionService(db)
    if not await perm_service.is_superadmin(current_user.user_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superadmin access required",
        )
    return current_user
