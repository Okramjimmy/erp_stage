"""Pydantic schemas for User endpoints."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field


# ---------------------------------------------------------------------------
# Create / Update
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    """Schema for creating a new user."""

    username: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8, max_length=128, pattern=r"^[a-z0-9_]+$")
    department: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=50)
    is_superadmin: bool = False


class UserUpdate(BaseModel):
    """Schema for updating profile fields (no username/password changes here)."""

    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    department: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=50)


class UserPasswordChange(BaseModel):
    """Schema for changing a user's own password."""

    current_password: str = Field(..., min_length=1)
    new_password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)


class UserPhotoUpdate(BaseModel):
    """Schema for setting the MinIO photo key after a successful upload."""

    profile_photo_url: str = Field(..., max_length=500)


# ---------------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------------

class UserLoginRequest(BaseModel):
    """Schema for login request."""

    username: str = Field(..., description="Username or email address")
    password: str


# ---------------------------------------------------------------------------
# Responses
# ---------------------------------------------------------------------------

class UserResponse(BaseModel):
    """Schema for user response — never exposes hashed_password."""

    user_id: str
    username: str
    email: str
    full_name: str
    department: Optional[str] = None
    phone: Optional[str] = None
    profile_photo_url: Optional[str] = None
    is_active: bool
    is_superadmin: bool
    created_at: datetime
    updated_at: datetime
    # Populated by UserService.get_user_with_roles()
    roles: List[str] = []

    class Config:
        from_attributes = True


class UserListItem(BaseModel):
    """Lightweight user row for admin list view."""

    user_id: str
    username: str
    email: str
    full_name: str
    department: Optional[str] = None
    phone: Optional[str] = None
    profile_photo_url: Optional[str] = None
    is_active: bool
    is_superadmin: bool
    roles: List[str] = []

    class Config:
        from_attributes = True
