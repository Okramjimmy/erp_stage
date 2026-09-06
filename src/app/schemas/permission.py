from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class StagePermissionCreate(BaseModel):
    """Schema for creating Stage permission."""

    role_name: str = Field(..., min_length=1, max_length=100)
    location_id: Optional[str] = None
    department_id: Optional[str] = None
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
    location_id: Optional[str] = None
    department_id: Optional[str] = None
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
    location_id: Optional[str] = None
    department_id: Optional[str] = None
    can_view: bool = False
    can_create_records: bool = False
    can_edit: bool = False
    can_delete: bool = False
    can_edit_records: bool = False
    can_delete_records: bool = False
    can_submit: bool = False
    can_verify: bool = False
    can_cancel: bool = False
    can_amend: bool = False
    can_manage_permissions: bool = False


class FormTypePermissionUpdate(BaseModel):
    """Schema for updating Form Type permission."""

    can_view: Optional[bool] = None
    can_create_records: Optional[bool] = None
    can_edit: Optional[bool] = None
    can_delete: Optional[bool] = None
    can_edit_records: Optional[bool] = None
    can_delete_records: Optional[bool] = None
    can_submit: Optional[bool] = None
    can_verify: Optional[bool] = None
    can_cancel: Optional[bool] = None
    can_amend: Optional[bool] = None
    can_manage_permissions: Optional[bool] = None


class FormTypePermissionResponse(BaseModel):
    """Schema for Form Type permission response."""

    permission_id: int
    form_type_id: str
    role_name: str
    location_id: Optional[str] = None
    department_id: Optional[str] = None
    can_view: bool
    can_create_records: bool
    can_edit: bool
    can_delete: bool
    can_edit_records: bool
    can_delete_records: bool
    can_submit: bool
    can_verify: bool
    can_cancel: bool
    can_amend: bool
    can_manage_permissions: bool
    granted_by: Optional[str] = None
    granted_at: datetime

    class Config:
        from_attributes = True


class CategoryPermissionCreate(BaseModel):
    """Schema for creating a FormType-category permission (project-scoped)."""

    role_name: str = Field(..., min_length=1, max_length=100)
    location_id: Optional[str] = None
    department_id: Optional[str] = None
    can_view: bool = False
    can_create_records: bool = False
    can_edit: bool = False
    can_delete: bool = False
    can_edit_records: bool = False
    can_delete_records: bool = False
    can_submit: bool = False
    can_verify: bool = False
    can_cancel: bool = False
    can_amend: bool = False
    can_manage_permissions: bool = False


class CategoryPermissionUpdate(BaseModel):
    """Schema for updating a FormType-category permission."""

    can_view: Optional[bool] = None
    can_create_records: Optional[bool] = None
    can_edit: Optional[bool] = None
    can_delete: Optional[bool] = None
    can_edit_records: Optional[bool] = None
    can_delete_records: Optional[bool] = None
    can_submit: Optional[bool] = None
    can_verify: Optional[bool] = None
    can_cancel: Optional[bool] = None
    can_amend: Optional[bool] = None
    can_manage_permissions: Optional[bool] = None


class CategoryPermissionResponse(BaseModel):
    """Schema for FormType-category permission response."""

    permission_id: int
    stage_id: str
    category: str
    role_name: str
    location_id: Optional[str] = None
    department_id: Optional[str] = None
    can_view: bool
    can_create_records: bool
    can_edit: bool
    can_delete: bool
    can_edit_records: bool
    can_delete_records: bool
    can_submit: bool
    can_verify: bool
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
    category_permissions: List[CategoryPermissionResponse]
    form_type_permissions: List[FormTypePermissionResponse]
    users_count: int


class RoleSetCreate(BaseModel):
    """Schema for creating a new RoleSet."""

    name: str = Field(..., min_length=1, max_length=150)
    description: Optional[str] = Field(None, max_length=500)
    role_names: List[str] = Field(default_factory=list, description="Initial member roles")


class RoleSetUpdate(BaseModel):
    """Schema for updating a RoleSet. `role_names`, when given, fully
    replaces the current membership."""

    name: Optional[str] = None
    description: Optional[str] = None
    role_names: Optional[List[str]] = None


class RoleSetResponse(BaseModel):
    """Schema for RoleSet response."""

    role_set_id: str
    name: str
    description: Optional[str] = None
    role_names: List[str]
    created_at: datetime
    created_by: Optional[str] = None

    class Config:
        from_attributes = True


class StageRoleSetAssign(BaseModel):
    """Schema for setting (or clearing) a stage's own RoleSet."""

    role_set_id: Optional[str] = Field(None, description="None clears the override — the stage inherits from its nearest ancestor")


class EffectiveRoleSetResponse(BaseModel):
    """Schema for a stage's resolved (possibly inherited) RoleSet."""

    stage_id: str
    role_set_id: Optional[str] = None
    role_set_name: Optional[str] = None
    source_stage_id: Optional[str] = Field(None, description="Which stage in the ancestor chain owns the governing RoleSet")
    unrestricted: bool = Field(..., description="True if no RoleSet was found anywhere up the chain — any role is assignable")
    role_names: Optional[List[str]] = None


class ProjectRolesUpdate(BaseModel):
    """Schema for fully replacing a project's Roles roster."""

    role_names: List[str] = Field(default_factory=list)


class ProjectRolesResponse(BaseModel):
    """Schema for a project's current Roles roster."""

    stage_id: str
    role_names: List[str]


class ProjectMemberAdd(BaseModel):
    """Schema for adding a user to a project's Members roster."""

    user_id: str = Field(..., min_length=1, max_length=100)


class ProjectMemberResponse(BaseModel):
    """Schema for a user in a project's Members roster."""

    user_id: str
    username: str


class UserProjectRoleCreate(BaseModel):
    """Schema for assigning a role to a user, scoped to a project (stage).

    A `stage_id` of None grants the role globally (applies everywhere) —
    only permitted for system-wide roles such as 'superadmin'.
    """

    user_id: str = Field(..., min_length=1, max_length=100)
    role_name: str = Field(..., min_length=1, max_length=100)
    stage_id: Optional[str] = None


class UserProjectRoleResponse(BaseModel):
    """Schema for a single (user, project, role) assignment row."""

    id: int
    user_id: str
    stage_id: Optional[str] = None
    role_id: int
    role_name: str
    assigned_at: datetime
    assigned_by: Optional[str] = None

    class Config:
        from_attributes = True


class ProjectRoleAssignmentResponse(BaseModel):
    """Schema for a resolved project/role assignment, used in stage-member
    views. `source` distinguishes a direct grant on the stage from one
    inherited through a parent project, or a global grant."""

    user_id: str
    username: Optional[str] = None
    stage_id: Optional[str] = None
    stage_name: Optional[str] = None
    role_name: str
    source: str  # "direct" | "inherited" | "global"
    granted_from_stage_id: Optional[str] = None
    assigned_at: Optional[datetime] = None
    assigned_by: Optional[str] = None


class UserAccessResponse(BaseModel):
    """Schema for user access response."""

    accessible_stage_ids: List[str]
    accessible_form_type_ids: List[str]
    total_count: int


class StageAndFormTypePermissionsResponse(BaseModel):
    """Schema for returning a stage's own, category, and linked form-type permissions."""

    stage_permissions: List[StagePermissionResponse]
    category_permissions: List[CategoryPermissionResponse]
    form_type_permissions: List[FormTypePermissionResponse]
