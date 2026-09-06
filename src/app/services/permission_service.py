"""Permission service for hierarchical, project-scoped access control."""

import datetime
import logging
import uuid
from typing import Dict, List, Optional, Set

from sqlalchemy import and_, or_, select, text, func, cast, String
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.cache import cache
from src.app.models.permission import (
    CategoryPermission,
    FormTypePermission,
    ProjectMember,
    ProjectRole,
    Role,
    RoleSet,
    RoleSetRole,
    StagePermission,
    UserProjectRole,
)
from src.app.models import User
from src.app.models.stage import Stage
from src.app.schemas.permission import (
    CategoryPermissionCreate,
    CategoryPermissionResponse,
    EffectiveRoleSetResponse,
    FormTypePermissionCreate,
    FormTypePermissionResponse,
    ProjectMemberAdd,
    ProjectMemberResponse,
    ProjectRoleAssignmentResponse,
    ProjectRolesResponse,
    ProjectRolesUpdate,
    RoleCreate,
    RoleResponse,
    RoleSetCreate,
    RoleSetResponse,
    RoleSetUpdate,
    StagePermissionCreate,
    StagePermissionResponse,
    UserAccessResponse,
    UserProjectRoleCreate,
    UserProjectRoleResponse,
)
from src.config import settings
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY

logger = logging.getLogger(__name__)


class PermissionService:
    """Service for permission management with hierarchical, project-scoped visibility."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Stage permissions (CRUD) — unchanged
    # ------------------------------------------------------------------

    async def grant_stage_permission(
        self,
        stage_id: str,
        permission_data: StagePermissionCreate,
        granted_by: Optional[str] = None,
    ) -> StagePermissionResponse:
        """Grant stage permission to a role."""
        # Check if permission already exists
        existing = await self.db.execute(
            select(StagePermission).where(
                and_(
                    StagePermission.stage_id == stage_id,
                    StagePermission.role_name == permission_data.role_name,
                    StagePermission.location_id == permission_data.location_id,
                    StagePermission.department_id == permission_data.department_id,
                )
            )
        )
        existing_perm = existing.scalar_one_or_none()

        if existing_perm:
            # Update existing permission
            existing_perm.can_view = permission_data.can_view
            existing_perm.can_create = permission_data.can_create
            existing_perm.can_edit = permission_data.can_edit
            existing_perm.can_delete = permission_data.can_delete
            existing_perm.can_manage_permissions = (
                permission_data.can_manage_permissions
            )
            existing_perm.granted_by = granted_by

            await self.db.commit()
            await self.db.refresh(existing_perm)

            # Invalidate cache
            await cache.delete_pattern(f"permission:{permission_data.role_name}:*")

            return StagePermissionResponse.model_validate(existing_perm)

        # Create new permission
        new_permission = StagePermission(
            stage_id=stage_id,
            role_name=permission_data.role_name,
            location_id=permission_data.location_id,
            department_id=permission_data.department_id,
            can_view=permission_data.can_view,
            can_create=permission_data.can_create,
            can_edit=permission_data.can_edit,
            can_delete=permission_data.can_delete,
            can_manage_permissions=permission_data.can_manage_permissions,
            granted_by=granted_by,
        )

        self.db.add(new_permission)
        await self.db.commit()
        await self.db.refresh(new_permission)

        # Invalidate cache
        await cache.delete_pattern(f"permission:{permission_data.role_name}:*")

        return StagePermissionResponse.model_validate(new_permission)

    async def revoke_stage_permission(
        self,
        stage_id: str,
        role_name: str,
        location_id: Optional[str] = None,
        department_id: Optional[str] = None,
    ) -> Dict[str, str]:
        """Revoke stage permission from a role."""
        result = await self.db.execute(
            select(StagePermission).where(
                and_(
                    StagePermission.stage_id == stage_id,
                    StagePermission.role_name == role_name,
                    StagePermission.location_id == location_id,
                    StagePermission.department_id == department_id,
                )
            )
        )
        permission = result.scalar_one_or_none()

        if not permission:
            raise ValueError(
                f"Permission for role {role_name} on stage {stage_id} not found"
            )

        await self.db.delete(permission)
        await self.db.commit()

        # Invalidate cache
        await cache.delete_pattern(f"permission:{role_name}:*")

        return {"revoked": f"{role_name} on {stage_id}"}

    async def revoke_form_type_permission(
        self,
        form_type_id: str,
        role_name: str,
        location_id: Optional[str] = None,
        department_id: Optional[str] = None,
    ) -> Dict[str, str]:
        """Revoke form type permission from a role."""
        result = await self.db.execute(
            select(FormTypePermission).where(
                and_(
                    FormTypePermission.form_type_id == form_type_id,
                    FormTypePermission.role_name == role_name,
                    FormTypePermission.location_id == location_id,
                    FormTypePermission.department_id == department_id,
                )
            )
        )
        permission = result.scalar_one_or_none()

        if not permission:
            raise ValueError(
                f"Permission for role {role_name} on form type {form_type_id} not found"
            )

        await self.db.delete(permission)
        await self.db.commit()

        # Invalidate cache
        await cache.delete_pattern(f"permission:{role_name}:*")

        return {"revoked": f"{role_name} on {form_type_id}"}

    async def grant_form_type_permission(
        self,
        form_type_id: str,
        permission_data: FormTypePermissionCreate,
        granted_by: Optional[str] = None,
    ) -> FormTypePermissionResponse:
        """Grant form type permission to a role."""
        # Check if permission already exists
        existing = await self.db.execute(
            select(FormTypePermission).where(
                and_(
                    FormTypePermission.form_type_id == form_type_id,
                    FormTypePermission.role_name == permission_data.role_name,
                    FormTypePermission.location_id == permission_data.location_id,
                    FormTypePermission.department_id == permission_data.department_id,
                )
            )
        )
        existing_perm = existing.scalar_one_or_none()

        if existing_perm:
            # Update existing permission
            existing_perm.can_view = permission_data.can_view
            existing_perm.can_create_records = permission_data.can_create_records
            existing_perm.can_edit = permission_data.can_edit
            existing_perm.can_delete = permission_data.can_delete
            existing_perm.can_edit_records = permission_data.can_edit_records
            existing_perm.can_delete_records = permission_data.can_delete_records
            existing_perm.can_submit = permission_data.can_submit
            existing_perm.can_verify = permission_data.can_verify
            existing_perm.can_cancel = permission_data.can_cancel
            existing_perm.can_amend = permission_data.can_amend
            existing_perm.can_manage_permissions = (
                permission_data.can_manage_permissions
            )
            existing_perm.granted_by = granted_by

            await self.db.commit()
            await self.db.refresh(existing_perm)

            # Invalidate cache
            await cache.delete_pattern(f"permission:{permission_data.role_name}:*")

            return FormTypePermissionResponse.model_validate(existing_perm)

        # Create new permission
        new_permission = FormTypePermission(
            form_type_id=form_type_id,
            role_name=permission_data.role_name,
            location_id=permission_data.location_id,
            department_id=permission_data.department_id,
            can_view=permission_data.can_view,
            can_create_records=permission_data.can_create_records,
            can_edit=permission_data.can_edit,
            can_delete=permission_data.can_delete,
            can_edit_records=permission_data.can_edit_records,
            can_delete_records=permission_data.can_delete_records,
            can_submit=permission_data.can_submit,
            can_verify=permission_data.can_verify,
            can_cancel=permission_data.can_cancel,
            can_amend=permission_data.can_amend,
            can_manage_permissions=permission_data.can_manage_permissions,
            granted_by=granted_by,
        )

        self.db.add(new_permission)
        await self.db.commit()
        await self.db.refresh(new_permission)

        # Invalidate cache
        await cache.delete_pattern(f"permission:{permission_data.role_name}:*")

        return FormTypePermissionResponse.model_validate(new_permission)

    # ------------------------------------------------------------------
    # Category permissions (CRUD) — new tier: project (stage) + FormType.group
    # ------------------------------------------------------------------

    async def grant_category_permission(
        self,
        stage_id: str,
        category: str,
        permission_data: CategoryPermissionCreate,
        granted_by: Optional[str] = None,
    ) -> CategoryPermissionResponse:
        """Grant a FormType-category permission to a role, scoped to a project (stage)."""
        existing = await self.db.execute(
            select(CategoryPermission).where(
                and_(
                    CategoryPermission.stage_id == stage_id,
                    CategoryPermission.category == category,
                    CategoryPermission.role_name == permission_data.role_name,
                    CategoryPermission.location_id == permission_data.location_id,
                    CategoryPermission.department_id == permission_data.department_id,
                )
            )
        )
        existing_perm = existing.scalar_one_or_none()

        if existing_perm:
            existing_perm.can_view = permission_data.can_view
            existing_perm.can_create_records = permission_data.can_create_records
            existing_perm.can_edit = permission_data.can_edit
            existing_perm.can_delete = permission_data.can_delete
            existing_perm.can_edit_records = permission_data.can_edit_records
            existing_perm.can_delete_records = permission_data.can_delete_records
            existing_perm.can_submit = permission_data.can_submit
            existing_perm.can_verify = permission_data.can_verify
            existing_perm.can_cancel = permission_data.can_cancel
            existing_perm.can_amend = permission_data.can_amend
            existing_perm.can_manage_permissions = permission_data.can_manage_permissions
            existing_perm.granted_by = granted_by

            await self.db.commit()
            await self.db.refresh(existing_perm)
            await cache.delete_pattern(f"permission:{permission_data.role_name}:*")
            return CategoryPermissionResponse.model_validate(existing_perm)

        new_permission = CategoryPermission(
            stage_id=stage_id,
            category=category,
            role_name=permission_data.role_name,
            location_id=permission_data.location_id,
            department_id=permission_data.department_id,
            can_view=permission_data.can_view,
            can_create_records=permission_data.can_create_records,
            can_edit=permission_data.can_edit,
            can_delete=permission_data.can_delete,
            can_edit_records=permission_data.can_edit_records,
            can_delete_records=permission_data.can_delete_records,
            can_submit=permission_data.can_submit,
            can_verify=permission_data.can_verify,
            can_cancel=permission_data.can_cancel,
            can_amend=permission_data.can_amend,
            can_manage_permissions=permission_data.can_manage_permissions,
            granted_by=granted_by,
        )
        self.db.add(new_permission)
        await self.db.commit()
        await self.db.refresh(new_permission)
        await cache.delete_pattern(f"permission:{permission_data.role_name}:*")
        return CategoryPermissionResponse.model_validate(new_permission)

    async def revoke_category_permission(
        self,
        stage_id: str,
        category: str,
        role_name: str,
        location_id: Optional[str] = None,
        department_id: Optional[str] = None,
    ) -> Dict[str, str]:
        """Revoke a category permission from a role."""
        result = await self.db.execute(
            select(CategoryPermission).where(
                and_(
                    CategoryPermission.stage_id == stage_id,
                    CategoryPermission.category == category,
                    CategoryPermission.role_name == role_name,
                    CategoryPermission.location_id == location_id,
                    CategoryPermission.department_id == department_id,
                )
            )
        )
        permission = result.scalar_one_or_none()
        if not permission:
            raise ValueError(
                f"Category permission for role {role_name} on {stage_id}/{category} not found"
            )
        await self.db.delete(permission)
        await self.db.commit()
        await cache.delete_pattern(f"permission:{role_name}:*")
        return {"revoked": f"{role_name} on {stage_id}/{category}"}

    async def list_category_permissions(
        self,
        stage_id: Optional[str] = None,
        category: Optional[str] = None,
        role_name: Optional[str] = None,
        location_id: Optional[str] = None,
        department_id: Optional[str] = None,
    ) -> List[CategoryPermissionResponse]:
        """List category permissions, optionally filtered."""
        query = select(CategoryPermission)
        if stage_id:
            query = query.where(CategoryPermission.stage_id == stage_id)
        if category:
            query = query.where(CategoryPermission.category == category)
        if role_name:
            query = query.where(CategoryPermission.role_name == role_name)
        if location_id == "null" or location_id is None:
            query = query.where(CategoryPermission.location_id.is_(None))
        else:
            query = query.where(CategoryPermission.location_id == location_id)
        if department_id == "null" or department_id is None:
            query = query.where(CategoryPermission.department_id.is_(None))
        else:
            query = query.where(CategoryPermission.department_id == department_id)
        result = await self.db.execute(query)
        permissions = result.scalars().all()
        return [CategoryPermissionResponse.model_validate(p) for p in permissions]

    # ------------------------------------------------------------------
    # Roles
    # ------------------------------------------------------------------

    async def create_role(
        self, role_data: RoleCreate, created_by: Optional[str] = None
    ) -> RoleResponse:
        """Create a new role and persist it in the roles table."""
        existing = await self.db.execute(
            select(Role).where(Role.role_name == role_data.role_name)
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Role '{role_data.role_name}' already exists")

        new_role = Role(
            role_name=role_data.role_name,
            description=role_data.description,
            created_by=created_by,
        )
        self.db.add(new_role)
        await self.db.commit()
        await self.db.refresh(new_role)

        logger.info(f"Created role: {role_data.role_name} by {created_by}")
        return RoleResponse.model_validate(new_role)

    # ------------------------------------------------------------------
    # RoleSets — reusable per-stage governing role bundles
    # ------------------------------------------------------------------

    async def create_role_set(
        self, data: RoleSetCreate, created_by: Optional[str] = None
    ) -> RoleSetResponse:
        """Create a new RoleSet and its initial role membership."""
        existing = await self.db.execute(
            select(RoleSet).where(RoleSet.name == data.name)
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"RoleSet '{data.name}' already exists")

        role_ids = await self._role_ids_for_names(data.role_names)

        role_set = RoleSet(
            role_set_id=f"roleset_{uuid.uuid4().hex[:12]}",
            name=data.name,
            description=data.description,
            created_by=created_by,
        )
        self.db.add(role_set)
        await self.db.flush()

        for role_id in role_ids:
            self.db.add(RoleSetRole(role_set_id=role_set.role_set_id, role_id=role_id))

        await self.db.commit()
        await self.db.refresh(role_set)
        logger.info(f"Created role set: {data.name} by {created_by}")
        return RoleSetResponse.model_validate(role_set.to_dict())

    async def list_role_sets(self) -> List[RoleSetResponse]:
        """List all RoleSets with their member roles."""
        result = await self.db.execute(select(RoleSet).order_by(RoleSet.name))
        role_sets = result.scalars().all()
        return [RoleSetResponse.model_validate(rs.to_dict()) for rs in role_sets]

    async def update_role_set(
        self, role_set_id: str, data: RoleSetUpdate
    ) -> RoleSetResponse:
        """Update a RoleSet's name/description, and fully replace its role
        membership if `role_names` is given."""
        result = await self.db.execute(
            select(RoleSet).where(RoleSet.role_set_id == role_set_id)
        )
        role_set = result.scalar_one_or_none()
        if not role_set:
            raise ValueError(f"RoleSet '{role_set_id}' not found")

        if data.name is not None:
            role_set.name = data.name
        if data.description is not None:
            role_set.description = data.description

        if data.role_names is not None:
            role_ids = await self._role_ids_for_names(data.role_names)
            existing_result = await self.db.execute(
                select(RoleSetRole).where(RoleSetRole.role_set_id == role_set_id)
            )
            for rsr in existing_result.scalars().all():
                await self.db.delete(rsr)
            for role_id in role_ids:
                self.db.add(RoleSetRole(role_set_id=role_set_id, role_id=role_id))

        await self.db.commit()
        await self.db.refresh(role_set)
        return RoleSetResponse.model_validate(role_set.to_dict())

    async def delete_role_set(self, role_set_id: str) -> Dict[str, object]:
        """Delete a RoleSet. Stages pointing at it fall back to inheritance
        (ON DELETE SET NULL); role_set_roles rows cascade automatically."""
        result = await self.db.execute(
            select(RoleSet).where(RoleSet.role_set_id == role_set_id)
        )
        role_set = result.scalar_one_or_none()
        if not role_set:
            raise ValueError(f"RoleSet '{role_set_id}' not found")

        stage_count_result = await self.db.execute(
            select(func.count()).where(Stage.role_set_id == role_set_id)
        )
        affected_stages = stage_count_result.scalar_one()

        await self.db.delete(role_set)
        await self.db.commit()

        return {"deleted": role_set_id, "stages_affected": affected_stages}

    async def set_stage_role_set(
        self, stage_id: str, role_set_id: Optional[str]
    ) -> Dict[str, object]:
        """Set (or clear, with None) a stage's own governing RoleSet."""
        stage_result = await self.db.execute(
            select(Stage).where(Stage.stage_id == stage_id)
        )
        stage = stage_result.scalar_one_or_none()
        if not stage:
            raise ValueError(f"Stage '{stage_id}' not found")

        if role_set_id is not None:
            role_set_result = await self.db.execute(
                select(RoleSet.role_set_id).where(RoleSet.role_set_id == role_set_id)
            )
            if role_set_result.scalar_one_or_none() is None:
                raise ValueError(f"RoleSet '{role_set_id}' not found")

        stage.role_set_id = role_set_id
        await self.db.commit()
        return {"stage_id": stage_id, "role_set_id": role_set_id}

    async def get_effective_role_set(self, stage_id: str) -> EffectiveRoleSetResponse:
        """Resolve the RoleSet governing a stage: its own if set, else the
        nearest ancestor's, else unrestricted (any role assignable) — the
        same nearest-ancestor-wins walk used by every other cascade in
        this file, but over `role_set_id` instead of role grants."""
        stage_result = await self.db.execute(
            select(Stage).where(Stage.stage_id == stage_id)
        )
        stage = stage_result.scalar_one_or_none()
        if not stage:
            return EffectiveRoleSetResponse(stage_id=stage_id, unrestricted=True)

        candidate_ids = [stage_id] + list(reversed(stage.lineage_path or []))
        candidates_result = await self.db.execute(
            select(Stage.stage_id, Stage.role_set_id)
            .where(Stage.stage_id.in_(candidate_ids))
        )
        role_set_by_stage = {row.stage_id: row.role_set_id for row in candidates_result}

        for candidate_id in candidate_ids:
            role_set_id = role_set_by_stage.get(candidate_id)
            if role_set_id:
                role_set_result = await self.db.execute(
                    select(RoleSet).where(RoleSet.role_set_id == role_set_id)
                )
                role_set = role_set_result.scalar_one_or_none()
                if role_set:
                    return EffectiveRoleSetResponse(
                        stage_id=stage_id,
                        role_set_id=role_set.role_set_id,
                        role_set_name=role_set.name,
                        source_stage_id=candidate_id,
                        unrestricted=False,
                        role_names=[r.role_name for r in role_set.roles],
                    )

        return EffectiveRoleSetResponse(stage_id=stage_id, unrestricted=True)

    async def _role_ids_for_names(self, role_names: List[str]) -> List[int]:
        """Resolve role names to role_ids, raising if any don't exist."""
        if not role_names:
            return []
        result = await self.db.execute(select(Role).where(Role.role_name.in_(role_names)))
        roles = {r.role_name: r.role_id for r in result.scalars().all()}
        missing = set(role_names) - set(roles)
        if missing:
            raise ValueError(f"Role(s) not found: {', '.join(sorted(missing))}")
        return [roles[name] for name in role_names]

    # ------------------------------------------------------------------
    # Project rosters — Roles/Members buckets scoping a whole project
    # ------------------------------------------------------------------

    def _resolve_project_stage_id(self, stage: Stage) -> Optional[str]:
        """Resolve the owning project (depth-1 Stage) for any stage in its
        subtree, mirroring the pattern already used at
        stage_service.py's wbs-prefix ancestor lookup: lineage_path[0] is
        always the hidden 'stage_system' root, so lineage_path[1] is the
        project for anything below depth 1. Returns None for the root
        itself (depth 0) or an orphaned stage with no lineage."""
        if stage.depth_level == 1:
            return stage.stage_id
        if stage.depth_level > 1 and stage.lineage_path and len(stage.lineage_path) > 1:
            return stage.lineage_path[1]
        return None

    async def set_project_roles(
        self, project_stage_id: str, role_names: List[str]
    ) -> ProjectRolesResponse:
        """Fully replace a project's Roles roster."""
        stage = await self._get_project_stage_or_raise(project_stage_id)
        role_ids = await self._role_ids_for_names(role_names)

        existing_result = await self.db.execute(
            select(ProjectRole).where(ProjectRole.stage_id == project_stage_id)
        )
        for pr in existing_result.scalars().all():
            await self.db.delete(pr)
        for role_id in role_ids:
            self.db.add(ProjectRole(stage_id=project_stage_id, role_id=role_id))

        await self.db.commit()
        return ProjectRolesResponse(stage_id=project_stage_id, role_names=role_names)

    async def list_project_roles(self, project_stage_id: str) -> List[str]:
        """List a project's Roles roster (empty = unrestricted)."""
        result = await self.db.execute(
            select(Role.role_name)
            .join(ProjectRole, ProjectRole.role_id == Role.role_id)
            .where(ProjectRole.stage_id == project_stage_id)
        )
        return [r[0] for r in result.all()]

    async def add_project_member(
        self, project_stage_id: str, user_id: str
    ) -> Dict[str, str]:
        """Add a user to a project's Members roster. Idempotent."""
        await self._get_project_stage_or_raise(project_stage_id)
        user_result = await self.db.execute(select(User.user_id).where(User.user_id == user_id))
        if user_result.scalar_one_or_none() is None:
            raise ValueError(f"User '{user_id}' not found")

        existing = await self.db.execute(
            select(ProjectMember).where(
                ProjectMember.stage_id == project_stage_id,
                ProjectMember.user_id == user_id,
            )
        )
        if not existing.scalar_one_or_none():
            self.db.add(ProjectMember(stage_id=project_stage_id, user_id=user_id))
            await self.db.commit()
        return {"stage_id": project_stage_id, "user_id": user_id}

    async def remove_project_member(
        self, project_stage_id: str, user_id: str
    ) -> Dict[str, str]:
        """Remove a user from a project's Members roster."""
        result = await self.db.execute(
            select(ProjectMember).where(
                ProjectMember.stage_id == project_stage_id,
                ProjectMember.user_id == user_id,
            )
        )
        member = result.scalar_one_or_none()
        if not member:
            raise ValueError(f"'{user_id}' is not a member of project '{project_stage_id}'")
        await self.db.delete(member)
        await self.db.commit()
        return {"stage_id": project_stage_id, "user_id": user_id}

    async def list_project_members(self, project_stage_id: str) -> List[ProjectMemberResponse]:
        """List a project's Members roster (empty = unrestricted)."""
        result = await self.db.execute(
            select(ProjectMember.user_id, User.username)
            .join(User, User.user_id == ProjectMember.user_id)
            .where(ProjectMember.stage_id == project_stage_id)
        )
        return [
            ProjectMemberResponse(user_id=row.user_id, username=row.username)
            for row in result.all()
        ]

    async def list_project_role_sets(self, project_stage_id: str) -> List[RoleSetResponse]:
        """List the global RoleSets that fit this project: every RoleSet
        when the project's Roles roster is unrestricted (empty), else only
        the ones whose member roles are a subset of that roster."""
        await self._get_project_stage_or_raise(project_stage_id)
        allowed_roles = set(await self.list_project_roles(project_stage_id))

        result = await self.db.execute(select(RoleSet).order_by(RoleSet.name))
        role_sets = result.scalars().all()
        if not allowed_roles:
            return [RoleSetResponse.model_validate(rs.to_dict()) for rs in role_sets]
        return [
            RoleSetResponse.model_validate(rs.to_dict())
            for rs in role_sets
            if set(r.role_name for r in rs.roles) <= allowed_roles
        ]

    async def _get_project_stage_or_raise(self, stage_id: str) -> Stage:
        result = await self.db.execute(select(Stage).where(Stage.stage_id == stage_id))
        stage = result.scalar_one_or_none()
        if not stage:
            raise ValueError(f"Stage '{stage_id}' not found")
        if stage.depth_level != 1:
            raise ValueError(
                "Only project-level stages (depth 1) can have a Roles/Members roster"
            )
        return stage

    async def is_superadmin(self, user_id: str) -> bool:
        """Check if user has a TRUE global (stage_id IS NULL) 'superadmin' assignment.

        Deliberately a dedicated, strict query rather than reusing
        get_user_roles() — 'superadmin' must never be derivable from a
        project-scoped assignment, since this gates a full bypass of every
        permission check in the system. Assignment is also enforced at
        write-time (assign_user_role) to only ever allow 'superadmin' with
        stage_id=None.
        """
        result = await self.db.execute(
            select(UserProjectRole.id)
            .join(Role, Role.role_id == UserProjectRole.role_id)
            .where(
                UserProjectRole.user_id == user_id,
                UserProjectRole.stage_id.is_(None),
                Role.role_name == "superadmin",
            )
            .limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def get_user_roles(
        self, user_id: str, stage_id: Optional[str] = None
    ) -> List[str]:
        """Get role names effective for a user.

        With no stage_id: the union of role names from every assignment the
        user holds anywhere (global + every project) — used for admin/UI
        display and for permission tables that aren't stage-scoped (e.g.
        FormTypePermission).

        With a stage_id: role-assignment cascade — a role granted on this
        stage, or on any ancestor of this stage, is effective here. This is
        what makes membership on a parent project imply access to child
        stages. Global (stage_id IS NULL) grants are deliberately excluded
        here — only 'superadmin' is ever global, and superadmin already
        bypasses stage checks entirely via is_superadmin(), so a global
        grant must never make a role "effective" on an arbitrary stage.
        """
        query = (
            select(Role.role_name)
            .join(UserProjectRole, UserProjectRole.role_id == Role.role_id)
            .where(UserProjectRole.user_id == user_id)
            .distinct()
        )

        if stage_id is not None:
            stage_result = await self.db.execute(
                select(Stage).where(Stage.stage_id == stage_id)
            )
            stage = stage_result.scalar_one_or_none()
            ancestor_ids = (stage.lineage_path + [stage_id]) if stage else [stage_id]
            query = query.where(UserProjectRole.stage_id.in_(ancestor_ids))

        result = await self.db.execute(query)
        return [r[0] for r in result.all()]

    async def assign_user_role(
        self, role_data: UserProjectRoleCreate, assigned_by: Optional[str] = None
    ) -> Dict[str, str]:
        """Assign a role to a user, scoped to a project (stage) — or globally
        when stage_id is None. Idempotent."""
        role_result = await self.db.execute(
            select(Role).where(Role.role_name == role_data.role_name)
        )
        role = role_result.scalar_one_or_none()
        if not role:
            raise ValueError(f"Role '{role_data.role_name}' does not exist. Create it first.")

        if role.role_name == "superadmin" and role_data.stage_id is not None:
            raise ValueError(
                "'superadmin' can only be assigned globally (omit stage_id)"
            )
        if role.role_name != "superadmin" and role_data.stage_id is None:
            raise ValueError(
                f"Role '{role_data.role_name}' must be assigned to a specific stage/project "
                "— only 'superadmin' can be assigned globally"
            )

        if role_data.stage_id is not None:
            stage_result = await self.db.execute(
                select(Stage).where(Stage.stage_id == role_data.stage_id)
            )
            stage = stage_result.scalar_one_or_none()
            if stage is None:
                raise ValueError(f"Stage '{role_data.stage_id}' not found")

            effective = await self.get_effective_role_set(role_data.stage_id)
            if not effective.unrestricted and role_data.role_name not in (effective.role_names or []):
                raise ValueError(
                    f"Role '{role_data.role_name}' is not part of the governing "
                    f"RoleSet '{effective.role_set_name}' for stage '{role_data.stage_id}' "
                    f"(governed by RoleSet at stage '{effective.source_stage_id}')"
                )

            project_stage_id = self._resolve_project_stage_id(stage)
            if project_stage_id:
                allowed_roles = await self.list_project_roles(project_stage_id)
                if allowed_roles and role_data.role_name not in allowed_roles:
                    raise ValueError(
                        f"Role '{role_data.role_name}' is not in project "
                        f"'{project_stage_id}'s Roles roster"
                    )
                allowed_members = await self.list_project_members(project_stage_id)
                if allowed_members and role_data.user_id not in {
                    m.user_id for m in allowed_members
                }:
                    raise ValueError(
                        f"User is not a member of project '{project_stage_id}' — "
                        "add them to the project's Members roster first"
                    )

        stage_filter = (
            UserProjectRole.stage_id == role_data.stage_id
            if role_data.stage_id is not None
            else UserProjectRole.stage_id.is_(None)
        )
        existing = await self.db.execute(
            select(UserProjectRole).where(
                and_(
                    UserProjectRole.user_id == role_data.user_id,
                    UserProjectRole.role_id == role.role_id,
                    stage_filter,
                )
            )
        )
        if existing.scalar_one_or_none():
            return {"status": "already_assigned", "role": role_data.role_name}

        self.db.add(UserProjectRole(
            user_id=role_data.user_id,
            stage_id=role_data.stage_id,
            role_id=role.role_id,
            assigned_by=assigned_by,
        ))

        await self.db.commit()
        await cache.delete(f"user:{role_data.user_id}:visible_stages")
        return {"status": "assigned", "role": role_data.role_name}

    async def revoke_project_role(
        self, user_id: str, role_name: str, stage_id: Optional[str] = None
    ) -> Dict[str, str]:
        """Revoke a single (user, stage, role) assignment. stage_id=None
        targets the global assignment for that role."""
        role_result = await self.db.execute(
            select(Role).where(Role.role_name == role_name)
        )
        role = role_result.scalar_one_or_none()
        if not role:
            raise ValueError(f"Role '{role_name}' not found")

        stage_filter = (
            UserProjectRole.stage_id == stage_id
            if stage_id is not None
            else UserProjectRole.stage_id.is_(None)
        )
        result = await self.db.execute(
            select(UserProjectRole).where(
                and_(
                    UserProjectRole.user_id == user_id,
                    UserProjectRole.role_id == role.role_id,
                    stage_filter,
                )
            )
        )
        assignment = result.scalar_one_or_none()
        if not assignment:
            scope = f"at stage {stage_id}" if stage_id else "(global)"
            raise ValueError(f"Assignment for role '{role_name}' on user {user_id} {scope} not found")

        await self.db.delete(assignment)
        await self.db.commit()
        await cache.delete(f"user:{user_id}:visible_stages")
        return {"revoked": f"{role_name} for {user_id}", "stage_id": stage_id}

    async def list_user_project_roles(self, user_id: str) -> List[UserProjectRoleResponse]:
        """List all raw (user, stage, role) assignment rows for a user."""
        result = await self.db.execute(
            select(UserProjectRole).where(UserProjectRole.user_id == user_id)
        )
        rows = result.scalars().all()
        return [
            UserProjectRoleResponse(
                id=r.id,
                user_id=r.user_id,
                stage_id=r.stage_id,
                role_id=r.role_id,
                role_name=r.role.role_name if r.role else "",
                assigned_at=r.assigned_at,
                assigned_by=r.assigned_by,
            )
            for r in rows
        ]

    async def list_stage_members(self, stage_id: str) -> List[ProjectRoleAssignmentResponse]:
        """List users effectively assigned to this stage: direct grants on
        this stage, grants inherited from ancestor stages, and global grants.

        When this stage has an effective RoleSet (its own, or inherited from
        an ancestor), membership is filtered to roles that RoleSet actually
        contains — an assignment made before the RoleSet existed, or before
        it was edited to drop that role, no longer counts as membership
        here. True global grants (stage_id IS NULL — superadmin) are always
        kept: superadmin bypasses RoleSet governance the same way it
        bypasses every other permission check."""
        stage_result = await self.db.execute(select(Stage).where(Stage.stage_id == stage_id))
        stage = stage_result.scalar_one_or_none()
        if not stage:
            raise ValueError(f"Stage '{stage_id}' not found")

        ancestor_ids = stage.lineage_path or []
        conditions = [UserProjectRole.stage_id == stage_id, UserProjectRole.stage_id.is_(None)]
        if ancestor_ids:
            conditions.append(UserProjectRole.stage_id.in_(ancestor_ids))

        result = await self.db.execute(
            select(UserProjectRole, User.username)
            .join(User, User.user_id == UserProjectRole.user_id)
            .where(or_(*conditions))
        )
        rows = result.all()

        members = []
        for r, username in rows:
            if r.stage_id == stage_id:
                source, granted_from = "direct", None
            elif r.stage_id is None:
                source, granted_from = "global", None
            else:
                source, granted_from = "inherited", r.stage_id

            members.append(ProjectRoleAssignmentResponse(
                user_id=r.user_id,
                username=username,
                stage_id=stage_id,
                stage_name=stage.stage_name,
                role_name=r.role.role_name if r.role else "",
                source=source,
                granted_from_stage_id=granted_from,
                assigned_at=r.assigned_at,
                assigned_by=r.assigned_by,
            ))

        effective = await self.get_effective_role_set(stage_id)
        if not effective.unrestricted:
            allowed_roles = set(effective.role_names or [])
            members = [
                m for m in members
                if m.source == "global" or m.role_name in allowed_roles
            ]

        return members

    # ------------------------------------------------------------------
    # Bulk cascade helpers
    # ------------------------------------------------------------------

    async def _effective_roles_per_stage(self, user_id: str) -> Dict[str, Set[str]]:
        """Bulk-compute, for every stage, the set of role names effective for
        this user there: role-assignment cascade — a project-role granted on
        a stage or any of its ancestors is effective on that stage (and
        every descendant). Global (stage_id IS NULL) grants are excluded —
        only 'superadmin' is ever global, and superadmin bypasses this
        cascade entirely via is_superadmin(), so a global grant must never
        make a role "effective" on an arbitrary stage."""
        rows_result = await self.db.execute(
            select(UserProjectRole.stage_id, Role.role_name)
            .join(Role, Role.role_id == UserProjectRole.role_id)
            .where(UserProjectRole.user_id == user_id)
        )
        rows = rows_result.all()

        direct_by_stage: Dict[str, Set[str]] = {}
        for sid, name in rows:
            if sid is not None:
                direct_by_stage.setdefault(sid, set()).add(name)

        stages_result = await self.db.execute(select(Stage).order_by(Stage.depth_level))
        stages = stages_result.scalars().all()

        effective: Dict[str, Set[str]] = {}
        for s in stages:
            parent_roles = (
                effective.get(s.parent_stage_id, set())
                if s.parent_stage_id
                else set()
            )
            effective[s.stage_id] = parent_roles | direct_by_stage.get(s.stage_id, set())

        return effective

    async def _permission_cascade_per_role(
        self,
        role_names: Set[str],
        sorted_stages: List[Stage],
        user_location_id: Optional[str],
        user_department_id: Optional[str],
    ) -> Dict[str, Dict[str, Dict[str, bool]]]:
        """Bulk-compute, for every stage and every given role name, the
        cascaded StagePermission booleans (a grant to a role on an ancestor
        stage applies to all its descendants). Kept per-role — not flattened
        across roles — so it can be safely recombined against a per-stage
        effective-role-set that varies by branch of the tree. Flattening
        here would let a role's grant on an unrelated stage leak into a
        subtree the user was never given that role in."""
        empty_perm = {
            "view": False, "create": False, "edit": False,
            "delete": False, "manage_permissions": False,
        }
        if not role_names:
            return {s.stage_id: {} for s in sorted_stages}

        result = await self.db.execute(
            select(StagePermission).where(
                and_(
                    StagePermission.role_name.in_(role_names),
                    or_(StagePermission.location_id.is_(None), StagePermission.location_id == user_location_id),
                    or_(StagePermission.department_id.is_(None), StagePermission.department_id == user_department_id),
                )
            )
        )
        direct_perms = result.scalars().all()

        direct_map: Dict[str, Dict[str, Dict[str, bool]]] = {}
        for sp in direct_perms:
            role_map = direct_map.setdefault(sp.stage_id, {})
            perm = role_map.setdefault(sp.role_name, dict(empty_perm))
            perm["view"] = perm["view"] or sp.can_view
            perm["create"] = perm["create"] or sp.can_create
            perm["edit"] = perm["edit"] or sp.can_edit
            perm["delete"] = perm["delete"] or sp.can_delete
            perm["manage_permissions"] = perm["manage_permissions"] or sp.can_manage_permissions

        cascade: Dict[str, Dict[str, Dict[str, bool]]] = {}
        for s in sorted_stages:
            sid = s.stage_id
            parent_map = cascade.get(s.parent_stage_id, {}) if s.parent_stage_id else {}
            resolved: Dict[str, Dict[str, bool]] = {}
            for role_name in role_names:
                parent_perm = parent_map.get(role_name, empty_perm)
                own_perm = direct_map.get(sid, {}).get(role_name, empty_perm)
                resolved[role_name] = {k: (parent_perm[k] or own_perm[k]) for k in empty_perm}
            cascade[sid] = resolved

        return cascade

    async def _category_cascade_per_role(
        self,
        role_names: Set[str],
        categories: Set[str],
        sorted_stages: List[Stage],
        user_location_id: Optional[str],
        user_department_id: Optional[str],
    ) -> Dict[str, Dict[str, Dict[str, Dict[str, bool]]]]:
        """Bulk-compute cascaded CategoryPermission booleans, keyed
        [category][stage_id][role_name] -> perms dict. Each perms dict
        includes a synthetic "_has_grant" key marking whether any
        category-tier row for that role exists on this stage or an
        ancestor — used to decide whether the category tier overrides the
        stage-tier fallback, mirroring check_form_type_permission's
        per-tier "presence overrides" rule."""
        perm_keys = [
            "view", "create_records", "edit", "delete", "edit_records",
            "delete_records", "submit", "verify", "cancel", "amend", "manage_permissions",
        ]
        empty_perm = {k: False for k in perm_keys}
        empty_perm["_has_grant"] = False

        result: Dict[str, Dict[str, Dict[str, Dict[str, bool]]]] = {c: {} for c in categories}
        if not role_names or not categories:
            return result

        rows_result = await self.db.execute(
            select(CategoryPermission).where(
                and_(
                    CategoryPermission.role_name.in_(role_names),
                    CategoryPermission.category.in_(categories),
                    or_(CategoryPermission.location_id.is_(None), CategoryPermission.location_id == user_location_id),
                    or_(CategoryPermission.department_id.is_(None), CategoryPermission.department_id == user_department_id),
                )
            )
        )
        direct_perms = rows_result.scalars().all()

        direct_map: Dict[str, Dict[str, Dict[str, Dict[str, bool]]]] = {}
        for cp in direct_perms:
            role_map = direct_map.setdefault(cp.category, {}).setdefault(cp.stage_id, {})
            perm = role_map.setdefault(cp.role_name, dict(empty_perm))
            perm["_has_grant"] = True
            perm["view"] = perm["view"] or cp.can_view
            perm["create_records"] = perm["create_records"] or cp.can_create_records
            perm["edit"] = perm["edit"] or cp.can_edit
            perm["delete"] = perm["delete"] or cp.can_delete
            perm["edit_records"] = perm["edit_records"] or cp.can_edit_records
            perm["delete_records"] = perm["delete_records"] or cp.can_delete_records
            perm["submit"] = perm["submit"] or cp.can_submit
            perm["verify"] = perm["verify"] or cp.can_verify
            perm["cancel"] = perm["cancel"] or cp.can_cancel
            perm["amend"] = perm["amend"] or cp.can_amend
            perm["manage_permissions"] = perm["manage_permissions"] or cp.can_manage_permissions

        for category in categories:
            cat_direct = direct_map.get(category, {})
            cascade: Dict[str, Dict[str, Dict[str, bool]]] = {}
            for s in sorted_stages:
                sid = s.stage_id
                parent_map = cascade.get(s.parent_stage_id, {}) if s.parent_stage_id else {}
                resolved: Dict[str, Dict[str, bool]] = {}
                for role_name in role_names:
                    parent_perm = parent_map.get(role_name, empty_perm)
                    own_perm = cat_direct.get(sid, {}).get(role_name, empty_perm)
                    resolved[role_name] = {k: (parent_perm[k] or own_perm[k]) for k in empty_perm}
                cascade[sid] = resolved
            result[category] = cascade

        return result

    # ------------------------------------------------------------------
    # Permission checks
    # ------------------------------------------------------------------

    async def get_visible_stages(self, user_id: str) -> List[str]:
        """
        Get all visible stage IDs for a user.

        Superadmins can see ALL stages. Regular users see a stage if they
        have an effective role there (via the project-membership cascade)
        that also has can_view (via the permission-definition cascade) on
        that stage or an ancestor.
        """
        # Superadmins can see everything
        if await self.is_superadmin(user_id):
            result = await self.db.execute(select(Stage.stage_id))
            return [r[0] for r in result.all()]

        # Try cache first
        cache_key = f"user:{user_id}:visible_stages"
        cached = await cache.get(cache_key)
        if cached:
            return cached

        # Get user details
        user_stmt = select(User).where(User.user_id == user_id)
        user_res = await self.db.execute(user_stmt)
        user = user_res.scalar_one_or_none()
        if not user:
            return []

        effective_roles = await self._effective_roles_per_stage(user_id)
        all_role_names: Set[str] = set().union(*effective_roles.values()) if effective_roles else set()
        if not all_role_names:
            await cache.set(cache_key, [], ttl=settings.cache_ttl_visible_stages)
            return []

        stages_result = await self.db.execute(select(Stage).order_by(Stage.depth_level))
        sorted_stages = stages_result.scalars().all()

        cascade = await self._permission_cascade_per_role(
            all_role_names, sorted_stages, user.location_id, user.dept
        )

        visible_stages = [
            sid
            for sid, roles in effective_roles.items()
            if any(cascade.get(sid, {}).get(r, {}).get("view", False) for r in roles)
        ]

        # Cache for 15 minutes
        await cache.set(
            cache_key, visible_stages, ttl=settings.cache_ttl_visible_stages
        )

        return visible_stages

    async def check_stage_permission(
        self, user_id: str, stage_id: str, permission_type: str = "can_view"
    ) -> bool:
        """
        Check if user has specific permission on a stage.

        Superadmins always have all permissions.
        """
        # Superadmins have all permissions
        if await self.is_superadmin(user_id):
            return True

        # Get user details
        user_stmt = select(User).where(User.user_id == user_id)
        user_res = await self.db.execute(user_stmt)
        user = user_res.scalar_one_or_none()
        if not user:
            return False

        user_location_id = user.location_id
        user_department_id = user.dept

        # Role-assignment cascade: only roles effective at this stage
        # (granted globally, on this stage, or on an ancestor project).
        roles = await self.get_user_roles(user_id, stage_id=stage_id)
        if not roles:
            return False

        # Get stage to check
        stage_result = await self.db.execute(
            select(Stage).where(Stage.stage_id == stage_id)
        )
        stage = stage_result.scalar_one_or_none()

        if not stage:
            return False

        # Permission-definition cascade: check if user has permission on
        # any ancestor (including this stage) — unchanged.
        ancestor_ids = stage.lineage_path + [stage_id]

        result = await self.db.execute(
            select(StagePermission).where(
                and_(
                    StagePermission.role_name.in_(roles),
                    StagePermission.stage_id.in_(ancestor_ids),
                    getattr(StagePermission, permission_type) == True,
                    or_(StagePermission.location_id.is_(None), StagePermission.location_id == user_location_id),
                    or_(StagePermission.department_id.is_(None), StagePermission.department_id == user_department_id),
                )
            )
        )

        has_permission = result.scalar_one_or_none() is not None
        return has_permission

    async def get_user_accessible_resources(self, user_id: str) -> UserAccessResponse:
        """Get all accessible resources (stages and form types) for a user."""
        visible_stage_ids = await self.get_visible_stages(user_id)

        # Get accessible form types (those in visible stages)
        if visible_stage_ids:
            from src.app.models.form_type import FormType
            from src.app.models.stage_form_type import StageFormType

            form_types_result = await self.db.execute(
                select(FormType.form_type_id)
                .join(StageFormType, StageFormType.form_type_id == FormType.form_type_id)
                .where(StageFormType.stage_id.in_(visible_stage_ids))
            )
            form_type_ids = [ft[0] for ft in form_types_result.all()]
        else:
            form_type_ids = []

        return UserAccessResponse(
            accessible_stage_ids=visible_stage_ids,
            accessible_form_type_ids=form_type_ids,
            total_count=len(visible_stage_ids) + len(form_type_ids),
        )

    async def list_stage_permissions(
        self,
        role_name: Optional[str] = None,
        location_id: Optional[str] = None,
        department_id: Optional[str] = None,
    ) -> List[StagePermissionResponse]:
        """List all stage permissions, optionally filtered by role, location, and department."""
        query = select(StagePermission)
        if role_name:
            query = query.where(StagePermission.role_name == role_name)
        if location_id == "null" or location_id is None:
            query = query.where(StagePermission.location_id.is_(None))
        else:
            query = query.where(StagePermission.location_id == location_id)
        if department_id == "null" or department_id is None:
            query = query.where(StagePermission.department_id.is_(None))
        else:
            query = query.where(StagePermission.department_id == department_id)
        result = await self.db.execute(query)
        permissions = result.scalars().all()
        return [StagePermissionResponse.model_validate(p) for p in permissions]

    async def list_form_type_permissions(
        self,
        role_name: Optional[str] = None,
        location_id: Optional[str] = None,
        department_id: Optional[str] = None,
    ) -> List[FormTypePermissionResponse]:
        """List all form type permissions, optionally filtered by role, location, and department."""
        query = select(FormTypePermission)
        if role_name:
            query = query.where(FormTypePermission.role_name == role_name)
        if location_id == "null" or location_id is None:
            query = query.where(FormTypePermission.location_id.is_(None))
        else:
            query = query.where(FormTypePermission.location_id == location_id)
        if department_id == "null" or department_id is None:
            query = query.where(FormTypePermission.department_id.is_(None))
        else:
            query = query.where(FormTypePermission.department_id == department_id)
        result = await self.db.execute(query)
        permissions = result.scalars().all()
        return [FormTypePermissionResponse.model_validate(p) for p in permissions]

    async def get_role_permissions(self, role_name: str) -> Dict:
        """Get all permissions for a specific role."""
        # Get stage permissions
        stage_result = await self.db.execute(
            select(StagePermission).where(StagePermission.role_name == role_name)
        )
        stage_permissions = stage_result.scalars().all()

        # Get category permissions
        category_result = await self.db.execute(
            select(CategoryPermission).where(CategoryPermission.role_name == role_name)
        )
        category_permissions = category_result.scalars().all()

        # Get form type permissions
        form_type_result = await self.db.execute(
            select(FormTypePermission).where(FormTypePermission.role_name == role_name)
        )
        form_type_permissions = form_type_result.scalars().all()

        # Collect all unique role names from stage/category/form tables
        stage_roles_res = await self.db.execute(select(StagePermission.role_name).distinct())
        cat_roles_res = await self.db.execute(select(CategoryPermission.role_name).distinct())
        ft_roles_res = await self.db.execute(select(FormTypePermission.role_name).distinct())
        all_roles = sorted(
            {r[0] for r in stage_roles_res.all()}
            | {r[0] for r in cat_roles_res.all()}
            | {r[0] for r in ft_roles_res.all()}
        )

        return {
            "role_name": role_name,
            "stage_permissions": [
                StagePermissionResponse.model_validate(p) for p in stage_permissions
            ],
            "category_permissions": [
                CategoryPermissionResponse.model_validate(p) for p in category_permissions
            ],
            "form_type_permissions": [
                FormTypePermissionResponse.model_validate(p)
                for p in form_type_permissions
            ],
            "all_roles": all_roles,
        }

    async def list_all_roles(self) -> List[Dict]:
        """List all roles with permission and user counts."""
        # Fetch all roles
        roles_result = await self.db.execute(
            select(Role).order_by(Role.role_name)
        )
        roles = roles_result.scalars().all()

        # Stage permission counts grouped by role
        stage_counts_result = await self.db.execute(
            select(
                StagePermission.role_name,
                func.count().label("count")
            ).group_by(StagePermission.role_name)
        )
        stage_counts = {row.role_name: row.count for row in stage_counts_result}

        # Category permission counts grouped by role
        cat_counts_result = await self.db.execute(
            select(
                CategoryPermission.role_name,
                func.count().label("count")
            ).group_by(CategoryPermission.role_name)
        )
        cat_counts = {row.role_name: row.count for row in cat_counts_result}

        # Form type permission counts grouped by role
        ft_counts_result = await self.db.execute(
            select(
                FormTypePermission.role_name,
                func.count().label("count")
            ).group_by(FormTypePermission.role_name)
        )
        ft_counts = {row.role_name: row.count for row in ft_counts_result}

        # User counts grouped by role_id — COUNT DISTINCT since a user can now
        # hold the same role at multiple projects (multiple rows).
        users_count_result = await self.db.execute(
            text("""
                SELECT role_id, COUNT(DISTINCT user_id) AS users_count
                FROM user_project_roles
                GROUP BY role_id
            """)
        )
        user_counts = {row.role_id: row.users_count for row in users_count_result}

        roles_info = []

        for role in roles:
            stage_count = stage_counts.get(role.role_name, 0)
            cat_count = cat_counts.get(role.role_name, 0)
            ft_count = ft_counts.get(role.role_name, 0)
            users_count = user_counts.get(role.role_id, 0)

            roles_info.append({
                "role_id": role.role_id,
                "role_name": role.role_name,
                "description": role.description,
                "stage_permissions_count": stage_count,
                "category_permissions_count": cat_count,
                "form_type_permissions_count": ft_count,
                "users_count": users_count,
                "total_permissions": stage_count + cat_count + ft_count,
            })

        return roles_info

    async def delete_role(self, role_name: str) -> Dict[str, str]:
        """Delete a role from the roles table.
        Cascades automatically delete user_project_roles rows.
        Stage/category/form-type permissions are deleted explicitly.
        """
        role_result = await self.db.execute(
            select(Role).where(Role.role_name == role_name)
        )
        role = role_result.scalar_one_or_none()
        if not role:
            raise ValueError(f"Role '{role_name}' not found")

        # Delete stage permissions
        stage_result = await self.db.execute(
            select(StagePermission).where(StagePermission.role_name == role_name)
        )
        stage_perms = stage_result.scalars().all()
        for perm in stage_perms:
            await self.db.delete(perm)

        # Delete category permissions
        category_result = await self.db.execute(
            select(CategoryPermission).where(CategoryPermission.role_name == role_name)
        )
        category_perms = category_result.scalars().all()
        for perm in category_perms:
            await self.db.delete(perm)

        # Delete form type permissions
        ft_result = await self.db.execute(
            select(FormTypePermission).where(FormTypePermission.role_name == role_name)
        )
        ft_perms = ft_result.scalars().all()
        for perm in ft_perms:
            await self.db.delete(perm)

        # Delete workflow assignments for this role
        from src.app.models.workflow_assignment import WorkflowAssignment
        wa_result = await self.db.execute(
            select(WorkflowAssignment).where(WorkflowAssignment.role == role_name)
        )
        wa_perms = wa_result.scalars().all()
        for wa in wa_perms:
            await self.db.delete(wa)

        # Update FormRecord rows (assigned_role = None)
        from src.app.models.form_record import FormRecord
        fr_result = await self.db.execute(
            select(FormRecord).where(FormRecord.assigned_role == role_name)
        )
        form_records = fr_result.scalars().all()
        for fr in form_records:
            fr.assigned_role = None

        # Update FormType workflow_data
        from src.app.models.form_type import FormType
        ft_type_result = await self.db.execute(
            select(FormType).where(FormType.workflow_data.isnot(None))
        )
        form_types = ft_type_result.scalars().all()
        for ft in form_types:
            wdata = dict(ft.workflow_data)
            changed = False
            if "transitions" in wdata:
                new_transitions = []
                for t in wdata["transitions"]:
                    new_t = dict(t)
                    if new_t.get("actor_role") == role_name:
                        new_t["actor_role"] = None
                        changed = True
                    if new_t.get("next_role") == role_name:
                        new_t["next_role"] = None
                        changed = True
                    new_transitions.append(new_t)
                wdata["transitions"] = new_transitions
            if changed:
                from sqlalchemy.orm.attributes import flag_modified
                ft.workflow_data = wdata
                flag_modified(ft, "workflow_data")

        # Delete UserProjectRole rows for this role (across all users/projects)
        upr_result = await self.db.execute(
            select(UserProjectRole).where(UserProjectRole.role_id == role.role_id)
        )
        user_project_roles = upr_result.scalars().all()
        affected_user_ids = {upr.user_id for upr in user_project_roles}
        for upr in user_project_roles:
            await self.db.delete(upr)

        # Delete the role row
        await self.db.delete(role)
        await self.db.commit()

        await cache.delete_pattern(f"permission:{role_name}:*")

        return {
            "deleted": role_name,
            "stage_permissions_deleted": len(stage_perms),
            "category_permissions_deleted": len(category_perms),
            "form_type_permissions_deleted": len(ft_perms),
            "workflow_assignments_deleted": len(wa_perms),
            "form_records_updated": len(form_records),
            "user_assignments_deleted": len(affected_user_ids),
        }

    async def rename_role(
        self, old_role_name: str, new_role_name: str
    ) -> Dict[str, str]:
        """Rename a role: update roles.role_name (single truth source), then
        propagate to stage/category/form-type permission rows, workflow
        assignments, form records, and form type workflow_data.
        user_project_roles rows don't need updating — they store role_id.
        """
        role_result = await self.db.execute(
            select(Role).where(Role.role_name == old_role_name)
        )
        role = role_result.scalar_one_or_none()
        if not role:
            raise ValueError(f"Role '{old_role_name}' not found")

        role.role_name = new_role_name

        # Update stage permissions (still store role_name string)
        stage_result = await self.db.execute(
            select(StagePermission).where(StagePermission.role_name == old_role_name)
        )
        stage_perms = stage_result.scalars().all()
        for perm in stage_perms:
            perm.role_name = new_role_name

        # Update category permissions
        category_result = await self.db.execute(
            select(CategoryPermission).where(CategoryPermission.role_name == old_role_name)
        )
        category_perms = category_result.scalars().all()
        for perm in category_perms:
            perm.role_name = new_role_name

        # Update form type permissions
        ft_result = await self.db.execute(
            select(FormTypePermission).where(
                FormTypePermission.role_name == old_role_name
            )
        )
        ft_perms = ft_result.scalars().all()
        for perm in ft_perms:
            perm.role_name = new_role_name

        # Update workflow assignments
        from src.app.models.workflow_assignment import WorkflowAssignment
        wa_result = await self.db.execute(
            select(WorkflowAssignment).where(WorkflowAssignment.role == old_role_name)
        )
        wa_perms = wa_result.scalars().all()
        for wa in wa_perms:
            wa.role = new_role_name

        # Update FormRecord rows
        from src.app.models.form_record import FormRecord
        fr_result = await self.db.execute(
            select(FormRecord).where(FormRecord.assigned_role == old_role_name)
        )
        form_records = fr_result.scalars().all()
        for fr in form_records:
            fr.assigned_role = new_role_name

        # Update FormType workflow_data
        from src.app.models.form_type import FormType
        ft_type_result = await self.db.execute(
            select(FormType).where(FormType.workflow_data.isnot(None))
        )
        form_types = ft_type_result.scalars().all()
        for ft in form_types:
            wdata = dict(ft.workflow_data)
            changed = False
            if "transitions" in wdata:
                new_transitions = []
                for t in wdata["transitions"]:
                    new_t = dict(t)
                    if new_t.get("actor_role") == old_role_name:
                        new_t["actor_role"] = new_role_name
                        changed = True
                    if new_t.get("next_role") == old_role_name:
                        new_t["next_role"] = new_role_name
                        changed = True
                    new_transitions.append(new_t)
                wdata["transitions"] = new_transitions
            if changed:
                from sqlalchemy.orm.attributes import flag_modified
                ft.workflow_data = wdata
                flag_modified(ft, "workflow_data")

        await self.db.commit()
        await cache.delete_pattern(f"permission:{old_role_name}:*")
        await cache.delete_pattern(f"permission:{new_role_name}:*")

        return {
            "renamed": f"{old_role_name} -> {new_role_name}",
            "stage_permissions_updated": len(stage_perms),
            "category_permissions_updated": len(category_perms),
            "form_type_permissions_updated": len(ft_perms),
            "workflow_assignments_updated": len(wa_perms),
            "form_records_updated": len(form_records),
            "user_assignments_updated": 0,  # stored by role_id — no update needed
        }

    async def check_form_type_permission(
        self, user_id: str, form_type_id: str, permission_type: str = "can_view"
    ) -> bool:
        """
        Check if user has specific permission on a form type.

        Resolution order: direct FormTypePermission (individual) ->
        CategoryPermission (project + FormType.group) -> StagePermission
        (cascading). At each tier, if the user's roles have ANY row for that
        tier, it overrides completely and we do not fall through further.
        If a user is a superadmin, they bypass all checks.
        """
        if await self.is_superadmin(user_id):
            return True

        # Get user details
        user_stmt = select(User).where(User.user_id == user_id)
        user_res = await self.db.execute(user_stmt)
        user = user_res.scalar_one_or_none()
        if not user:
            return False

        user_location_id = user.location_id
        user_department_id = user.dept

        roles_anywhere = await self.get_user_roles(user_id)
        if not roles_anywhere:
            return False

        # 1. Check direct form type permission (FormTypePermission has no
        # stage scoping, so this matches against roles held anywhere).
        direct_stmt = select(FormTypePermission).where(
            and_(
                FormTypePermission.role_name.in_(roles_anywhere),
                FormTypePermission.form_type_id == form_type_id,
                or_(FormTypePermission.location_id.is_(None), FormTypePermission.location_id == user_location_id),
                or_(FormTypePermission.department_id.is_(None), FormTypePermission.department_id == user_department_id),
            )
        )
        direct_res = await self.db.execute(direct_stmt)
        direct_perms = direct_res.scalars().all()

        if direct_perms:
            # If direct permissions are configured, they override everything else.
            for dp in direct_perms:
                if getattr(dp, permission_type) == True:
                    return True
            return False

        # 2 & 3. Check category, then stage permissions on mapped stages (if any)
        from src.app.models.stage_form_type import StageFormType
        from src.app.models.form_type import FormType

        ft_result = await self.db.execute(
            select(FormType).where(FormType.form_type_id == form_type_id)
        )
        form_type = ft_result.scalar_one_or_none()

        mapping_stmt = select(StageFormType.stage_id).where(StageFormType.form_type_id == form_type_id)
        mapping_res = await self.db.execute(mapping_stmt)
        mapped_stage_ids = [r[0] for r in mapping_res.all()]

        stage_perm = permission_type
        if permission_type == "can_create_records":
            stage_perm = "can_create"
        elif permission_type == "can_edit_records":
            stage_perm = "can_edit"
        elif permission_type == "can_delete_records":
            stage_perm = "can_delete"

        for stage_id in mapped_stage_ids:
            if form_type and form_type.group:
                roles_at_stage = await self.get_user_roles(user_id, stage_id=stage_id)
                if roles_at_stage:
                    stage_result = await self.db.execute(
                        select(Stage).where(Stage.stage_id == stage_id)
                    )
                    stage = stage_result.scalar_one_or_none()
                    ancestor_ids = (stage.lineage_path + [stage_id]) if stage else [stage_id]

                    cat_stmt = select(CategoryPermission).where(
                        and_(
                            CategoryPermission.role_name.in_(roles_at_stage),
                            CategoryPermission.stage_id.in_(ancestor_ids),
                            CategoryPermission.category == form_type.group,
                            or_(CategoryPermission.location_id.is_(None), CategoryPermission.location_id == user_location_id),
                            or_(CategoryPermission.department_id.is_(None), CategoryPermission.department_id == user_department_id),
                        )
                    )
                    cat_res = await self.db.execute(cat_stmt)
                    cat_perms = cat_res.scalars().all()

                    if cat_perms:
                        if any(getattr(cp, permission_type) for cp in cat_perms):
                            return True
                        # Category tier had rows for this stage but said no —
                        # don't fall through to the stage tier for this stage.
                        continue

            if await self.check_stage_permission(user_id, stage_id, stage_perm):
                return True

        return False

    async def get_user_permissions(self, user_id: str) -> Dict:
        """
        Get resolved permissions for stages and form types for the user.
        """
        from src.app.models.form_type import FormType
        from src.app.models.stage_form_type import StageFormType

        # 1. Fetch all stages & form types
        stages_res = await self.db.execute(select(Stage).order_by(Stage.depth_level))
        all_stages = stages_res.scalars().all()

        ft_res = await self.db.execute(select(FormType))
        all_fts = ft_res.scalars().all()

        if await self.is_superadmin(user_id):
            stages_perms = {
                s.stage_id: {
                    "view": True,
                    "create": True,
                    "edit": True,
                    "delete": True,
                    "manage_permissions": True,
                }
                for s in all_stages
            }
            form_types_perms = {
                ft.form_type_id: {
                    "view": True,
                    "create_records": True,
                    "edit": True,
                    "delete": True,
                    "edit_records": True,
                    "delete_records": True,
                    "submit": True,
                    "verify": True,
                    "cancel": True,
                    "amend": True,
                    "manage_permissions": True,
                }
                for ft in all_fts
            }
            return {"stages": stages_perms, "form_types": form_types_perms}

        # Get user details
        user_stmt = select(User).where(User.user_id == user_id)
        user_res = await self.db.execute(user_stmt)
        user = user_res.scalar_one_or_none()
        if not user:
            return {"stages": {}, "form_types": {}}

        user_location_id = user.location_id
        user_department_id = user.dept

        empty_stage_perm = {
            "view": False, "create": False, "edit": False,
            "delete": False, "manage_permissions": False,
        }
        empty_ft_perm = {
            "view": False, "create_records": False, "edit": False, "delete": False,
            "edit_records": False, "delete_records": False, "submit": False,
            "verify": False, "cancel": False, "amend": False, "manage_permissions": False,
        }

        effective_roles = await self._effective_roles_per_stage(user_id)
        all_role_names: Set[str] = set().union(*effective_roles.values()) if effective_roles else set()

        if not all_role_names:
            stages_perms = {s.stage_id: dict(empty_stage_perm) for s in all_stages}
            form_types_perms = {ft.form_type_id: dict(empty_ft_perm) for ft in all_fts}
            return {"stages": stages_perms, "form_types": form_types_perms}

        # 2. Resolve Stage permissions: per-role cascade combined with the
        # per-stage effective-role set (fixes the cross-branch leak a single
        # flattened role list would cause once roles are project-scoped).
        stage_cascade = await self._permission_cascade_per_role(
            all_role_names, all_stages, user_location_id, user_department_id
        )
        stages_perms: Dict[str, Dict[str, bool]] = {}
        for s in all_stages:
            sid = s.stage_id
            roles_here = effective_roles.get(sid, set())
            per_stage_cascade = stage_cascade.get(sid, {})
            resolved = dict(empty_stage_perm)
            for r in roles_here:
                rp = per_stage_cascade.get(r, empty_stage_perm)
                for k in resolved:
                    resolved[k] = resolved[k] or rp[k]
            stages_perms[sid] = resolved

        # 3. Get direct FormType permissions (global role match, unscoped by stage)
        ft_perms_res = await self.db.execute(
            select(FormTypePermission).where(
                and_(
                    FormTypePermission.role_name.in_(all_role_names),
                    or_(FormTypePermission.location_id.is_(None), FormTypePermission.location_id == user_location_id),
                    or_(FormTypePermission.department_id.is_(None), FormTypePermission.department_id == user_department_id),
                )
            )
        )
        direct_ft_perms = ft_perms_res.scalars().all()

        ft_perm_map: Dict[str, Dict[str, bool]] = {}
        for ftp in direct_ft_perms:
            ftid = ftp.form_type_id
            perm = ft_perm_map.setdefault(ftid, dict(empty_ft_perm))
            perm["view"] = perm["view"] or ftp.can_view
            perm["create_records"] = perm["create_records"] or ftp.can_create_records
            perm["edit"] = perm["edit"] or ftp.can_edit
            perm["delete"] = perm["delete"] or ftp.can_delete
            perm["edit_records"] = perm["edit_records"] or ftp.can_edit_records
            perm["delete_records"] = perm["delete_records"] or ftp.can_delete_records
            perm["submit"] = perm["submit"] or ftp.can_submit
            perm["verify"] = perm["verify"] or ftp.can_verify
            perm["cancel"] = perm["cancel"] or ftp.can_cancel
            perm["amend"] = perm["amend"] or ftp.can_amend
            perm["manage_permissions"] = perm["manage_permissions"] or ftp.can_manage_permissions

        # 4. Fetch StageFormType mapping
        mapping_res = await self.db.execute(select(StageFormType))
        mappings = mapping_res.scalars().all()
        ft_to_stages_map: Dict[str, List[str]] = {}
        for m in mappings:
            ft_to_stages_map.setdefault(m.form_type_id, []).append(m.stage_id)

        # 5. Category cascade for every FormType.group in use
        categories: Set[str] = {ft.group for ft in all_fts if ft.group}
        category_cascade = await self._category_cascade_per_role(
            all_role_names, categories, all_stages, user_location_id, user_department_id
        )

        # 6. Resolve FormType permissions: individual overrides completely;
        # else per mapped stage, category tier overrides completely; else stage tier.
        form_types_perms: Dict[str, Dict[str, bool]] = {}
        for ft in all_fts:
            ftid = ft.form_type_id
            if ftid in ft_perm_map:
                form_types_perms[ftid] = ft_perm_map[ftid]
                continue

            resolved = dict(empty_ft_perm)
            mapped_sids = ft_to_stages_map.get(ftid, [])
            for stage_id in mapped_sids:
                roles_here = effective_roles.get(stage_id, set())
                used_category_tier = False

                if ft.group and roles_here:
                    per_stage_cat = category_cascade.get(ft.group, {}).get(stage_id, {})
                    has_grant = any(
                        per_stage_cat.get(r, {}).get("_has_grant", False) for r in roles_here
                    )
                    if has_grant:
                        used_category_tier = True
                        for k in resolved:
                            resolved[k] = resolved[k] or any(
                                per_stage_cat.get(r, {}).get(k, False) for r in roles_here
                            )

                if not used_category_tier and stage_id in stages_perms:
                    sp = stages_perms[stage_id]
                    resolved["view"] = resolved["view"] or sp["view"]
                    resolved["create_records"] = resolved["create_records"] or sp["create"]
                    resolved["edit_records"] = resolved["edit_records"] or sp["edit"]
                    resolved["delete_records"] = resolved["delete_records"] or sp["delete"]
                    resolved["edit"] = resolved["edit"] or sp["edit"]
                    resolved["delete"] = resolved["delete"] or sp["delete"]
                    resolved["manage_permissions"] = resolved["manage_permissions"] or sp["manage_permissions"]

            form_types_perms[ftid] = resolved

        return {"stages": stages_perms, "form_types": form_types_perms}

    # ------------------------------------------------------------------
    # Superadmin Role Seeding
    # ------------------------------------------------------------------

    async def seed_superadmin_role(self) -> None:
        """
        Ensures a 'superadmin' role tracker exists, then grants it full permissions
        on every stage, form-type, and (stage, category) pair currently in the database.

        This is idempotent — safe to call on every startup. It upserts permissions
        rather than creating duplicates.
        """
        from src.app.models.form_type import FormType
        from src.app.models.stage_form_type import StageFormType

        ROLE = "superadmin"

        # Ensure the 'superadmin' role exists in the roles table
        existing_role = await self.db.execute(select(Role).where(Role.role_name == ROLE))
        if not existing_role.scalar_one_or_none():
            self.db.add(Role(
                role_name=ROLE,
                description="Full system access",
                created_by="system",
            ))
            await self.db.flush()

        # Grant full permissions on every stage
        stages_result = await self.db.execute(select(Stage))
        stages = stages_result.scalars().all()
        for stage in stages:
            existing = await self.db.execute(
                select(StagePermission).where(
                    StagePermission.stage_id == stage.stage_id,
                    StagePermission.role_name == ROLE,
                )
            )
            perm = existing.scalar_one_or_none()
            if perm:
                perm.can_view = True
                perm.can_create = True
                perm.can_edit = True
                perm.can_delete = True
                perm.can_manage_permissions = True
            else:
                self.db.add(StagePermission(
                    stage_id=stage.stage_id,
                    role_name=ROLE,
                    can_view=True,
                    can_create=True,
                    can_edit=True,
                    can_delete=True,
                    can_manage_permissions=True,
                    granted_by="system",
                ))

        # Grant full permissions on every form type
        ft_result = await self.db.execute(select(FormType))
        form_types = ft_result.scalars().all()
        for ft in form_types:
            existing = await self.db.execute(
                select(FormTypePermission).where(
                    FormTypePermission.form_type_id == ft.form_type_id,
                    FormTypePermission.role_name == ROLE,
                )
            )
            perm = existing.scalar_one_or_none()
            if perm:
                perm.can_view = True
                perm.can_create_records = True
                perm.can_edit = True
                perm.can_delete = True
                perm.can_edit_records = True
                perm.can_delete_records = True
                perm.can_submit = True
                perm.can_verify = True
                perm.can_cancel = True
                perm.can_amend = True
                perm.can_manage_permissions = True
            else:
                self.db.add(FormTypePermission(
                    form_type_id=ft.form_type_id,
                    role_name=ROLE,
                    can_view=True,
                    can_create_records=True,
                    can_edit=True,
                    can_delete=True,
                    can_edit_records=True,
                    can_delete_records=True,
                    can_submit=True,
                    can_verify=True,
                    can_cancel=True,
                    can_amend=True,
                    can_manage_permissions=True,
                    granted_by="system",
                ))

        # Grant full category permissions for every (stage, category) pair in
        # use, so the Permissions UI shows superadmin's category grants when
        # the admin selects role=superadmin. Functionally redundant since
        # is_superadmin() bypasses every check.
        mapping_result = await self.db.execute(
            select(StageFormType.stage_id, FormType.group)
            .join(FormType, FormType.form_type_id == StageFormType.form_type_id)
            .where(FormType.group.isnot(None))
            .distinct()
        )
        stage_category_pairs = mapping_result.all()

        cat_count = 0
        for stage_id, category in stage_category_pairs:
            existing = await self.db.execute(
                select(CategoryPermission).where(
                    CategoryPermission.stage_id == stage_id,
                    CategoryPermission.category == category,
                    CategoryPermission.role_name == ROLE,
                )
            )
            perm = existing.scalar_one_or_none()
            if perm:
                perm.can_view = True
                perm.can_create_records = True
                perm.can_edit = True
                perm.can_delete = True
                perm.can_edit_records = True
                perm.can_delete_records = True
                perm.can_submit = True
                perm.can_verify = True
                perm.can_cancel = True
                perm.can_amend = True
                perm.can_manage_permissions = True
            else:
                self.db.add(CategoryPermission(
                    stage_id=stage_id,
                    category=category,
                    role_name=ROLE,
                    can_view=True,
                    can_create_records=True,
                    can_edit=True,
                    can_delete=True,
                    can_edit_records=True,
                    can_delete_records=True,
                    can_submit=True,
                    can_verify=True,
                    can_cancel=True,
                    can_amend=True,
                    can_manage_permissions=True,
                    granted_by="system",
                ))
            cat_count += 1

        await self.db.commit()
        await cache.delete_pattern(f"permission:{ROLE}:*")
        logger.info(
            f"Seeded '{ROLE}' role with full permissions on {len(stages)} stages, "
            f"{len(form_types)} form types, and {cat_count} categories."
        )
