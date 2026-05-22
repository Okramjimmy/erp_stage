"""FormType service for managing dynamic form templates."""

import json
import logging
import uuid
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.cache import cache
from src.app.models.form_type import FormType
from src.app.models.permission import FormTypePermission
from src.app.models.stage import Stage
from src.app.models.stage_form_type import StageFormType
from src.app.schemas.form_type import (
    FormTypeCreate,
    FormTypeResponse,
    FormTypeUpdate,
    FormTypeWithSchema,
)
from src.config import settings

logger = logging.getLogger(__name__)


class FormTypeService:
    """Service for FormType operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def generate_form_type_id(prefix: str = "form") -> str:
        """Generate unique form type ID."""
        return f"{prefix}_{uuid.uuid4().hex[:12]}"

    async def create_form_type(
        self, form_data: FormTypeCreate, created_by: Optional[str] = None
    ) -> FormTypeResponse:
        """Create a new form type."""
        # Check for name conflicts
        existing = await self.db.execute(
            select(FormType).where(FormType.form_name == form_data.form_name)
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"FormType with name '{form_data.form_name}' already exists")

        # Create form type
        new_form_type = FormType(
            form_type_id=self.generate_form_type_id(),
            form_name=form_data.form_name,
            description=form_data.description,
            version=form_data.version,
            schema_reference=form_data.schema,  # JSONB accepts dict directly
            created_by=created_by,
        )

        self.db.add(new_form_type)
        await self.db.commit()
        await self.db.refresh(new_form_type)

        # Automatically grant all permissions to the 'superadmin' role
        await self._grant_superadmin_form_permission(new_form_type.form_type_id)

        return FormTypeResponse.model_validate(new_form_type)

    async def link_form_to_stage(
        self, form_type_id: str, stage_id: str, linked_by: Optional[str] = None
    ) -> dict:
        """Link a form type to a stage."""
        # Check if link already exists
        existing = await self.db.execute(
            select(StageFormType).where(
                StageFormType.stage_id == stage_id,
                StageFormType.form_type_id == form_type_id
            )
        )
        if existing.scalar_one_or_none():
            return {"status": "success", "message": "Already linked"}

        # Validate stage and form type exist
        stage_result = await self.db.execute(select(Stage).where(Stage.stage_id == stage_id))
        if not stage_result.scalar_one_or_none():
            raise ValueError(f"Stage {stage_id} not found")

        form_result = await self.db.execute(select(FormType).where(FormType.form_type_id == form_type_id))
        if not form_result.scalar_one_or_none():
            raise ValueError(f"FormType {form_type_id} not found")

        link = StageFormType(
            stage_id=stage_id,
            form_type_id=form_type_id,
            linked_by=linked_by
        )
        self.db.add(link)
        await self.db.commit()

        await cache.invalidate_stage_cache(stage_id)
        return {"status": "success", "message": f"Linked FormType {form_type_id} to Stage {stage_id}"}

    async def unlink_form_from_stage(self, form_type_id: str, stage_id: str) -> dict:
        """Unlink a form type from a stage."""
        result = await self.db.execute(
            select(StageFormType).where(
                StageFormType.stage_id == stage_id,
                StageFormType.form_type_id == form_type_id
            )
        )
        link = result.scalar_one_or_none()
        if not link:
            raise ValueError(f"Link between FormType {form_type_id} and Stage {stage_id} not found")

        await self.db.delete(link)
        await self.db.commit()

        await cache.invalidate_stage_cache(stage_id)
        return {"status": "success", "message": f"Unlinked FormType {form_type_id} from Stage {stage_id}"}

    async def _grant_superadmin_form_permission(self, form_type_id: str) -> None:
        """Grant full permissions for the 'superadmin' role on a given form type (idempotent)."""
        ROLE = "superadmin"
        existing = await self.db.execute(
            select(FormTypePermission).where(
                FormTypePermission.form_type_id == form_type_id,
                FormTypePermission.role_name == ROLE,
            )
        )
        perm = existing.scalar_one_or_none()
        if perm:
            perm.can_view = True
            perm.can_create = True
            perm.can_edit = True
            perm.can_delete = True
            perm.can_submit = True
            perm.can_cancel = True
            perm.can_amend = True
            perm.can_manage_permissions = True
        else:
            self.db.add(FormTypePermission(
                form_type_id=form_type_id,
                role_name=ROLE,
                can_view=True,
                can_create=True,
                can_edit=True,
                can_delete=True,
                can_submit=True,
                can_cancel=True,
                can_amend=True,
                can_manage_permissions=True,
                granted_by="system",
            ))
        await self.db.commit()
        logger.info(f"Auto-granted '{ROLE}' full permissions on form type {form_type_id}")

    async def get_form_type(self, form_type_id: str) -> Optional[FormTypeResponse]:
        """Get form type by ID."""
        result = await self.db.execute(
            select(FormType).where(FormType.form_type_id == form_type_id)
        )
        form_type = result.scalar_one_or_none()

        if not form_type:
            return None

        return FormTypeResponse.model_validate(form_type)

    async def get_form_type_with_schema(
        self, form_type_id: str
    ) -> Optional[FormTypeWithSchema]:
        """Get form type with schema data."""
        result = await self.db.execute(
            select(FormType).where(FormType.form_type_id == form_type_id)
        )
        form_type = result.scalar_one_or_none()

        if not form_type:
            return None

        # JSONB returns dict directly, no parsing needed
        return FormTypeWithSchema.model_validate(form_type)

    async def get_form_types_by_stage(
        self, stage_id: str, skip: int = 0, limit: int = 100
    ) -> List[FormTypeResponse]:
        """Get all form types for a specific stage."""
        result = await self.db.execute(
            select(FormType)
            .join(StageFormType, StageFormType.form_type_id == FormType.form_type_id)
            .where(StageFormType.stage_id == stage_id)
            .order_by(FormType.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        form_types = result.scalars().all()

        return [FormTypeResponse.model_validate(ft) for ft in form_types]

    async def get_all_form_types(
        self, skip: int = 0, limit: int = 100
    ) -> List[FormTypeResponse]:
        """Get all form types with pagination."""
        result = await self.db.execute(
            select(FormType)
            .order_by(FormType.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        form_types = result.scalars().all()

        return [FormTypeResponse.model_validate(ft) for ft in form_types]

    async def get_all_form_types_with_schema(
        self, skip: int = 0, limit: int = 100
    ) -> List[FormTypeWithSchema]:
        """Get all form types with schema data for template selection."""
        result = await self.db.execute(
            select(FormType)
            .order_by(FormType.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        form_types = result.scalars().all()

        return [FormTypeWithSchema.model_validate(ft) for ft in form_types]

    async def update_form_type(
        self, form_type_id: str, form_data: FormTypeUpdate
    ) -> FormTypeResponse:
        """Update an existing form type."""
        result = await self.db.execute(
            select(FormType).where(FormType.form_type_id == form_type_id)
        )
        form_type = result.scalar_one_or_none()

        if not form_type:
            raise ValueError(f"FormType {form_type_id} not found")

        if form_data.form_name and form_data.form_name != form_type.form_name:
            # Check for name conflicts
            existing = await self.db.execute(
                select(FormType).where(FormType.form_name == form_data.form_name)
            )
            if existing.scalar_one_or_none():
                raise ValueError(f"FormType with name '{form_data.form_name}' already exists")
            form_type.form_name = form_data.form_name

        if form_data.version:
            form_type.version = form_data.version

        if form_data.schema is not None:
            form_type.schema_reference = form_data.schema  # JSONB accepts dict directly

        # Also support updating description if it's in the payload
        if hasattr(form_data, "description") and form_data.description is not None:
            form_type.description = form_data.description

        await self.db.commit()
        await self.db.refresh(form_type)

        return FormTypeResponse.model_validate(form_type)

    async def delete_form_type(self, form_type_id: str) -> dict:
        """Delete a form type."""
        result = await self.db.execute(
            select(FormType).where(FormType.form_type_id == form_type_id)
        )
        form_type = result.scalar_one_or_none()

        if not form_type:
            raise ValueError(f"FormType {form_type_id} not found")

        # Invalidate cache for all stages this form type was linked to
        stage_links = await self.db.execute(
            select(StageFormType.stage_id).where(StageFormType.form_type_id == form_type_id)
        )
        stage_ids = stage_links.scalars().all()

        await self.db.delete(form_type)
        await self.db.commit()

        # Invalidate caches
        for stage_id in stage_ids:
            await cache.invalidate_stage_cache(stage_id)

        return {"deleted_form_type_id": form_type_id}

    async def search_form_types(
        self, query: str, limit: int = 50
    ) -> List[FormTypeResponse]:
        """Search form types by name."""
        result = await self.db.execute(
            select(FormType)
            .where(FormType.form_name.ilike(f"%{query}%"))
            .order_by(FormType.form_name)
            .limit(limit)
        )
        form_types = result.scalars().all()

        return [FormTypeResponse.model_validate(ft) for ft in form_types]
