"""Auth API endpoints — login, logout, me."""

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.auth import clear_session, get_current_user, set_session
from src.app.database import get_db
from src.app.schemas.user import UserLoginRequest, UserResponse
from src.app.services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/login", response_model=UserResponse)
async def login(
    data: UserLoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate with username + password.
    Sets an HTTP-only signed session cookie on success.
    Returns the full UserResponse including roles array.
    """
    service = UserService(db)
    user = await service.authenticate(data.username, data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password",
        )

    # Write user_id into the signed session cookie
    set_session(request, user.user_id)

    # Build response with roles
    result = await service.get_user_with_roles(user.user_id)
    if not result:
        raise HTTPException(status_code=500, detail="Session error after login")
    user_obj, roles = result

    return UserResponse(
        **user_obj.to_dict(),
        roles=roles,
    )


@router.post("/logout", status_code=204)
async def logout(request: Request):
    """Clear the session cookie."""
    clear_session(request)
    return Response(status_code=204)


@router.get("/me", response_model=UserResponse)
async def me(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(get_current_user),
):
    """
    Return the currently authenticated user with their roles list.
    Used by base.html's fetchUser() to populate the sidebar.
    """
    service = UserService(db)
    result = await service.get_user_with_roles(current_user.user_id)
    if not result:
        raise HTTPException(status_code=404, detail="User not found")
    user_obj, roles = result
    return UserResponse(**user_obj.to_dict(), roles=roles)
