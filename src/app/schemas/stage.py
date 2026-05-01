from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class StageBase(BaseModel):
    """Base schema for Stage."""

    stage_name: str = Field(..., min_length=1, max_length=255)
    parent_stage_id: Optional[str] = None
    visibility_scope: str = Field(
        default="private", pattern="^(public|private|restricted)$"
    )


class StageCreate(StageBase):
    """Schema for creating a Stage."""

    pass


class StageUpdate(BaseModel):
    """Schema for updating a Stage."""

    stage_name: Optional[str] = Field(None, min_length=1, max_length=255)
    visibility_scope: Optional[str] = Field(
        None, pattern="^(public|private|restricted)$"
    )


class StageResponse(BaseModel):
    """Schema for Stage response."""

    stage_id: str
    stage_name: str
    parent_stage_id: Optional[str] = None
    stage_path: str
    depth_level: int
    lineage_path: List[str]
    children_count: int
    formtype_count: int
    is_root: bool
    is_leaf: bool
    visibility_scope: str
    created_by: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    metadata_reference: Optional[str] = None

    class Config:
        from_attributes = True


class FormTypeRef(BaseModel):
    """Reference schema for Form Type."""

    form_type_id: str
    form_name: str
    version: Optional[str] = None

    class Config:
        from_attributes = True

    @field_validator("version", mode="before")
    @classmethod
    def empty_string_to_none(cls, v):
        """Convert empty string to None for version field."""
        if v == "":
            return None
        return v


class StageTreeNode(StageResponse):
    """Schema for Stage tree node with nested children."""

    children: List["StageTreeNode"] = []
    form_types: List["FormTypeRef"] = []

    class Config:
        from_attributes = True


class StageMoveRequest(BaseModel):
    """Schema for moving a Stage."""

    target_parent_id: str
    options: Optional[dict] = Field(
        default={"update_lineage": True, "update_master_metadata": True}
    )


class StageMoveResponse(BaseModel):
    """Schema for Stage move response."""

    stage_id: str
    old_path: str
    new_path: str
    affected_stages_count: int
    affected_formtypes_count: int
    operation_duration_ms: Optional[float] = None


class StageTreeResponse(BaseModel):
    """Schema for Stage tree response."""

    stage_id: str
    stage_name: str
    depth: int
    path: str
    children: List[StageTreeNode]


# Forward references for recursive models
StageTreeNode.model_rebuild()
StageTreeResponse.model_rebuild()
