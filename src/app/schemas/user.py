"""Pydantic schemas for User endpoints."""

from datetime import datetime
from typing import List, Optional
import re
from pydantic import BaseModel, EmailStr, Field, field_validator

# ---------------------------------------------------------------------------
# Create / Update
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    """Schema for creating a new user."""

    username: str = Field(..., min_length=3, max_length=100)
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=8, max_length=128)
    department: Optional[str] = Field(None, max_length=100)
    location: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=50)
    manager_id: Optional[str] = None
    roles: Optional[List[str]] = None

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        # 1. Check for spaces (matches your original [^\s])
        if re.search(r"\s", v):
            raise ValueError("Password must not contain spaces")
        
        # 2. Check for at least one uppercase letter
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
            
        # 3. Check for at least one digit
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one number")
            
        # 4. Check for at least one special character
        # (Using a simpler character class since we aren't doing complex look-aheads)
        if not re.search(r"[!@#$%^&*()_+={}\[\]:;\"'<>,.?/\\|`~-]", v):
            raise ValueError("Password must contain at least one special character")
            
        return v


class UserUpdate(BaseModel):
    """Schema for updating profile fields (no username/password changes here)."""

    full_name: Optional[str] = Field(None, min_length=1, max_length=255)
    email: Optional[EmailStr] = None
    department: Optional[str] = Field(None, max_length=100)
    location: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, max_length=50)
    manager_id: Optional[str] = None
    is_active: Optional[bool] = None


class UserPasswordChange(BaseModel):
    """Schema for changing a user's own password."""

    current_password: str = Field(..., min_length=1)
    password: str = Field(..., min_length=8, max_length=128)
    confirm_password: str = Field(..., min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        # 1. Check for spaces (matches your original [^\s])
        if re.search(r"\s", v):
            raise ValueError("Password must not contain spaces")
        
        # 2. Check for at least one uppercase letter
        if not re.search(r"[A-Z]", v):
            raise ValueError("Password must contain at least one uppercase letter")
            
        # 3. Check for at least one digit
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one number")
            
        # 4. Check for at least one special character
        # (Using a simpler character class since we aren't doing complex look-aheads)
        if not re.search(r"[!@#$%^&*()_+={}\[\]:;\"'<>,.?/\\|`~-]", v):
            raise ValueError("Password must contain at least one special character")
            
        return v


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
    dept: Optional[str] = None
    department: Optional[str] = None
    location_id: Optional[str] = None
    location: Optional[str] = None
    phone: Optional[str] = None
    manager_id: Optional[str] = None
    profile_photo_url: Optional[str] = None
    is_active: bool
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
    dept: Optional[str] = None
    department: Optional[str] = None
    location_id: Optional[str] = None
    location: Optional[str] = None
    phone: Optional[str] = None
    manager_id: Optional[str] = None
    profile_photo_url: Optional[str] = None
    is_active: bool
    roles: List[str] = []

    class Config:
        from_attributes = True
