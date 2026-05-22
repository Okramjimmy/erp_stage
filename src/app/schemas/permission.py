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
    can_cancel: bool = False
    can_amend: bool = False
    can_manage_permissions: bool = False


class FormTypePermissionUpdate(BaseModel):
    """Schema for updating Form Type permission."""

    can_view: Optional[bool] = None
    can_create: Optional[bool] = None
    can_edit: Optional[bool] = None
    can_delete: Optional[bool] = None
    can_submit: Optional[bool] = None
    can_cancel: Optional[bool] = None
    can_amend: Optional[bool] = None
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
    can_cancel: bool
    can_amend: bool
    can_manage_permissions: bool
    granted_by: Optional[str] = None
    granted_at: datetime

    class Config:
        from_attributes = True


class RoleCreate(BaseModel):
    """Schema for creating a new Role."""

    role_name: str = Field(..., min_length=1, max_length=100, pattern="^[a-z0-9_]+$")
    description: Optional[str] = Field(None, max_length=500)


class RoleResponse(BaseModel):
    """Schema for Role response."""

    role_name: str
    description: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True


class RolePermissionsResponse(BaseModel):
    """Schema for role with its permissions."""

    role_name: str
    description: Optional[str] = None
    stage_permissions: List[StagePermissionResponse]
    form_type_permissions: List[FormTypePermissionResponse]
    users_count: int


class UserRoleCreate(BaseModel):
    """Schema for assigning a role to a user."""

    user_id: str = Field(..., min_length=1, max_length=100)
    role_name: str = Field(..., min_length=1, max_length=100)


class UserRoleResponse(BaseModel):
    """Schema for User role assignment response."""

    user_id: str
    role_id: int
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


class StageAndFormTypePermissionsResponse(BaseModel):
    """Schema for returning both stage and its linked form types permissions."""
    
    stage_permissions: List[StagePermissionResponse]
    form_type_permissions: List[FormTypePermissionResponse]
