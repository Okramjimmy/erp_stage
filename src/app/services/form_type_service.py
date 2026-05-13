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
        # Validate stage exists
        stage_result = await self.db.execute(
            select(Stage).where(Stage.stage_id == form_data.stage_id)
        )
        stage = stage_result.scalar_one_or_none()

        if not stage:
            raise ValueError(f"Stage {form_data.stage_id} not found")

        # Generate form path
        form_path = f"{stage.stage_path}/{form_data.form_name}"

        # Check for path conflicts
        existing = await self.db.execute(
            select(FormType).where(FormType.form_path == form_path)
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Form path {form_path} already exists")

        # Create form type
        new_form_type = FormType(
            form_type_id=self.generate_form_type_id(),
            form_name=form_data.form_name,
            stage_id=form_data.stage_id,
            form_path=form_path,
            version=form_data.version,
            schema_reference=form_data.schema,  # JSONB accepts dict directly
            created_by=created_by,
        )

        self.db.add(new_form_type)
        await self.db.commit()
        await self.db.refresh(new_form_type)

        # Automatically grant all permissions to the 'superadmin' role
        await self._grant_superadmin_form_permission(new_form_type.form_type_id)

        # Invalidate caches
        await cache.invalidate_stage_cache(form_data.stage_id)

        return FormTypeResponse.model_validate(new_form_type)

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
            .where(FormType.stage_id == stage_id)
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

        # Update fields
        if form_data.form_name:
            form_type.form_name = form_data.form_name
            # Update path
            stage_result = await self.db.execute(
                select(Stage).where(Stage.stage_id == form_type.stage_id)
            )
            stage = stage_result.scalar_one()
            form_type.form_path = f"{stage.stage_path}/{form_data.form_name}"

        if form_data.version:
            form_type.version = form_data.version

        if form_data.schema is not None:
            form_type.schema_reference = form_data.schema  # JSONB accepts dict directly

        await self.db.commit()
        await self.db.refresh(form_type)

        # Invalidate cache
        await cache.invalidate_stage_cache(form_type.stage_id)

        return FormTypeResponse.model_validate(form_type)

    async def delete_form_type(self, form_type_id: str) -> dict:
        """Delete a form type."""
        result = await self.db.execute(
            select(FormType).where(FormType.form_type_id == form_type_id)
        )
        form_type = result.scalar_one_or_none()

        if not form_type:
            raise ValueError(f"FormType {form_type_id} not found")

        stage_id = form_type.stage_id

        await self.db.delete(form_type)
        await self.db.commit()

        # Invalidate cache
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
