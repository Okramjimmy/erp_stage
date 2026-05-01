from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class StagePermissionCreate(BaseModel):
    """Schema for creating Stage permission."""

    role_name: str = Field(..., min_length=1, max_length=100)
    can_view: bool = False
    can_create: bool = False
    can_edit: bool = False
    can_delete: bool = False
    can_manage_permissions: bool = False


class StagePermissionUpdate(BaseModel):
    """Schema for updating Stage permission."""

    can_view: Optional[bool] = None
    can_create: Optional[bool] = None
    can_edit: Optional[bool] = None
    can_delete: Optional[bool] = None
    can_manage_permissions: Optional[bool] = None


class StagePermissionResponse(BaseModel):
    """Schema for Stage permission response."""

    permission_id: int
    stage_id: str
    role_name: str
    can_view: bool
    can_create: bool
    can_edit: bool
    can_delete: bool
    can_manage_permissions: bool
    granted_by: Optional[str] = None
    granted_at: datetime

    class Config:
        from_attributes = True


class FormTypePermissionCreate(BaseModel):
    """Schema for creating Form Type permission."""

    role_name: str = Field(..., min_length=1, max_length=100)
    can_view: bool = False
    can_create: bool = False
    can_edit: bool = False
    can_delete: bool = False
    can_submit: bool = False
    can_manage_permissions: bool = False


class FormTypePermissionUpdate(BaseModel):
    """Schema for updating Form Type permission."""

    can_view: Optional[bool] = None
    can_create: Optional[bool] = None
    can_edit: Optional[bool] = None
    can_delete: Optional[bool] = None
    can_submit: Optional[bool] = None
    can_manage_permissions: Optional[bool] = None


class FormTypePermissionResponse(BaseModel):
    """Schema for Form Type permission response."""

    permission_id: int
    form_type_id: str
    role_name: str
    can_view: bool
    can_create: bool
    can_edit: bool
    can_delete: bool
    can_submit: bool
    can_manage_permissions: bool
    granted_by: Optional[str] = None
    granted_at: datetime

    class Config:
        from_attributes = True


class UserRoleCreate(BaseModel):
    """Schema for creating User role."""

    user_id: str = Field(..., min_length=1, max_length=100)
    role_name: str = Field(..., min_length=1, max_length=100)


class UserRoleResponse(BaseModel):
    """Schema for User role response."""

    user_id: str
    role_name: str
    assigned_at: datetime
    assigned_by: Optional[str] = None

    class Config:
        from_attributes = True


class UserAccessResponse(BaseModel):
    """Schema for user access response."""

    accessible_stage_ids: List[str]
    accessible_form_type_ids: List[str]
    total_count: int
