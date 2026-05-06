"""Permission service for hierarchical access control."""

import datetime
import logging
from typing import Dict, List, Optional, Set

from sqlalchemy import and_, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.cache import cache
from src.app.models.permission import FormTypePermission, Role, StagePermission, UserRole
from src.app.models.stage import Stage
from src.app.schemas.permission import (
    FormTypePermissionCreate,
    FormTypePermissionResponse,
    RoleCreate,
    RoleResponse,
    StagePermissionCreate,
    StagePermissionResponse,
    UserAccessResponse,
    UserRoleCreate,
)
from src.config import settings

logger = logging.getLogger(__name__)


class PermissionService:
    """Service for permission management with hierarchical visibility."""

    def __init__(self, db: AsyncSession):
        self.db = db

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
        self, stage_id: str, role_name: str
    ) -> Dict[str, str]:
        """Revoke stage permission from a role."""
        result = await self.db.execute(
            select(StagePermission).where(
                and_(
                    StagePermission.stage_id == stage_id,
                    StagePermission.role_name == role_name,
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
            existing_perm.can_submit = permission_data.can_submit
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
            can_view=permission_data.can_view,
            can_create=permission_data.can_create,
            can_edit=permission_data.can_edit,
            can_delete=permission_data.can_delete,
            can_submit=permission_data.can_submit,
            can_manage_permissions=permission_data.can_manage_permissions,
            granted_by=granted_by,
        )

        self.db.add(new_permission)
        await self.db.commit()
        await self.db.refresh(new_permission)

        # Invalidate cache
        await cache.delete_pattern(f"permission:{permission_data.role_name}:*")

        return FormTypePermissionResponse.model_validate(new_permission)

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

    async def get_user_roles(self, user_id: str) -> List[str]:
        """Get all role names for a user by resolving their role_ids JSONB array."""
        result = await self.db.execute(
            select(UserRole).where(UserRole.user_id == user_id)
        )
        row = result.scalar_one_or_none()
        if not row or not row.role_ids:
            return []
        names_result = await self.db.execute(
            select(Role.role_name).where(Role.role_id.in_(row.role_ids))
        )
        return [r[0] for r in names_result.all()]

    async def assign_user_role(
        self, role_data: UserRoleCreate, assigned_by: Optional[str] = None
    ) -> Dict[str, str]:
        """Assign a role to a user — resolves role_name → role_id, upserts into array."""
        role_result = await self.db.execute(
            select(Role).where(Role.role_name == role_data.role_name)
        )
        role = role_result.scalar_one_or_none()
        if not role:
            raise ValueError(f"Role '{role_data.role_name}' does not exist. Create it first.")

        result = await self.db.execute(
            select(UserRole).where(UserRole.user_id == role_data.user_id)
        )
        row = result.scalar_one_or_none()

        if row:
            existing = set(row.role_ids or [])
            if role.role_id in existing:
                return {"status": "already_assigned", "role": role_data.role_name}
            row.role_ids = sorted(existing | {role.role_id})
            row.assigned_by = assigned_by
        else:
            self.db.add(UserRole(
                user_id=role_data.user_id,
                role_ids=[role.role_id],
                assigned_by=assigned_by,
            ))

        await self.db.commit()
        await cache.delete(f"user:{role_data.user_id}:visible_stages")
        return {"status": "assigned", "role": role_data.role_name}

    async def get_visible_stages(self, user_id: str, is_superadmin: bool = False) -> List[str]:
        """
        Get all visible stage IDs for a user using lineage-based visibility.

        Superadmins can see ALL stages.
        Regular users see stages where they have direct permission and all descendants.
        """
        # Superadmins can see everything
        if is_superadmin:
            result = await self.db.execute(select(Stage.stage_id))
            return [r[0] for r in result.all()]

        # Try cache first
        cache_key = f"user:{user_id}:visible_stages"
        cached = await cache.get(cache_key)
        if cached:
            return cached

        # Get user roles
        roles = await self.get_user_roles(user_id)
        if not roles:
            return []

        # Get all stage permissions for user's roles
        result = await self.db.execute(
            select(StagePermission).where(StagePermission.role_name.in_(roles))
        )
        permissions = result.scalars().all()

        # Get stages where user has permission
        accessible_stage_ids: Set[str] = set()
        for perm in permissions:
            if perm.can_view:
                accessible_stage_ids.add(perm.stage_id)

        # Get all descendants using lineage
        # A stage is visible if ANY of its ancestors has a permission
        if accessible_stage_ids:
            # Query for stages where lineage contains any accessible stage
            stages_result = await self.db.execute(
                select(Stage.stage_id).where(
                    or_(
                        Stage.stage_id.in_(accessible_stage_ids),
                        Stage.lineage_path.overlap(list(accessible_stage_ids)),
                    )
                )
            )
            visible_stages = [s[0] for s in stages_result.all()]
        else:
            visible_stages = []

        # Cache for 15 minutes
        await cache.set(
            cache_key, visible_stages, ttl=settings.cache_ttl_visible_stages
        )

        return visible_stages

    async def check_stage_permission(
        self, user_id: str, stage_id: str, permission_type: str = "can_view",
        is_superadmin: bool = False
    ) -> bool:
        """
        Check if user has specific permission on a stage.

        Superadmins always have all permissions.
        Regular users: uses lineage-based visibility.
        """
        # Superadmins have all permissions
        if is_superadmin:
            return True

        # Get user roles
        roles = await self.get_user_roles(user_id)
        if not roles:
            return False

        # Get stage to check
        stage_result = await self.db.execute(
            select(Stage).where(Stage.stage_id == stage_id)
        )
        stage = stage_result.scalar_one_or_none()

        if not stage:
            return False

        # Check if user has permission on any ancestor (including this stage)
        # Build lineage including current stage
        ancestor_ids = stage.lineage_path + [stage_id]

        # Check permissions on all ancestors
        result = await self.db.execute(
            select(StagePermission).where(
                and_(
                    StagePermission.role_name.in_(roles),
                    StagePermission.stage_id.in_(ancestor_ids),
                    getattr(StagePermission, permission_type) == True,
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

            form_types_result = await self.db.execute(
                select(FormType.form_type_id).where(
                    FormType.stage_id.in_(visible_stage_ids)
                )
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
        self, role_name: Optional[str] = None
    ) -> List[StagePermissionResponse]:
        """List all stage permissions, optionally filtered by role."""
        query = select(StagePermission)
        if role_name:
            query = query.where(StagePermission.role_name == role_name)
        result = await self.db.execute(query)
        permissions = result.scalars().all()
        return [StagePermissionResponse.model_validate(p) for p in permissions]

    async def list_form_type_permissions(
        self, role_name: Optional[str] = None
    ) -> List[FormTypePermissionResponse]:
        """List all form type permissions, optionally filtered by role."""
        query = select(FormTypePermission)
        if role_name:
            query = query.where(FormTypePermission.role_name == role_name)
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

        # Get form type permissions
        form_type_result = await self.db.execute(
            select(FormTypePermission).where(FormTypePermission.role_name == role_name)
        )
        form_type_permissions = form_type_result.scalars().all()

        # Collect all unique role names from stage/form tables
        stage_roles_res = await self.db.execute(select(StagePermission.role_name).distinct())
        ft_roles_res = await self.db.execute(select(FormTypePermission.role_name).distinct())
        all_roles = sorted(
            {r[0] for r in stage_roles_res.all()}
            | {r[0] for r in ft_roles_res.all()}
        )

        return {
            "role_name": role_name,
            "stage_permissions": [
                StagePermissionResponse.model_validate(p) for p in stage_permissions
            ],
            "form_type_permissions": [
                FormTypePermissionResponse.model_validate(p)
                for p in form_type_permissions
            ],
            "all_roles": all_roles,
        }

    async def list_all_roles(self) -> List[Dict]:
        """List all roles from the roles table with permission and user counts."""
        roles_result = await self.db.execute(select(Role).order_by(Role.role_name))
        roles = roles_result.scalars().all()

        roles_info = []
        for role in roles:
            stage_count_result = await self.db.execute(
                select(StagePermission).where(StagePermission.role_name == role.role_name)
            )
            stage_count = len(stage_count_result.scalars().all())

            ft_count_result = await self.db.execute(
                select(FormTypePermission).where(FormTypePermission.role_name == role.role_name)
            )
            ft_count = len(ft_count_result.scalars().all())

            # Count users who have this role_id in their JSONB array
            users_count_result = await self.db.execute(
                text("SELECT COUNT(*) FROM user_roles WHERE role_ids @> CAST(:id_json AS jsonb)").bindparams(
                    id_json=f'[{role.role_id}]'
                )
            )
            users_count = users_count_result.scalar() or 0

            roles_info.append({
                "role_id": role.role_id,
                "role_name": role.role_name,
                "description": role.description,
                "stage_permissions_count": stage_count,
                "form_type_permissions_count": ft_count,
                "users_count": users_count,
                "total_permissions": stage_count + ft_count,
            })

        return roles_info

    async def delete_role(self, role_name: str) -> Dict[str, str]:
        """Delete a role from the roles table.
        Cascades automatically delete user_roles rows.
        Stage/form-type permissions are deleted explicitly.
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

        # Delete form type permissions
        ft_result = await self.db.execute(
            select(FormTypePermission).where(FormTypePermission.role_name == role_name)
        )
        ft_perms = ft_result.scalars().all()
        for perm in ft_perms:
            await self.db.delete(perm)

        # Update or delete UserRole rows
        users_result = await self.db.execute(
            select(UserRole).where(
                text("role_ids @> CAST(:id_json AS jsonb)").bindparams(id_json=f"[{role.role_id}]")
            )
        )
        user_roles = users_result.scalars().all()
        users_count = len(user_roles)

        for ur in user_roles:
            current_ids = ur.role_ids or []
            if role.role_id in current_ids:
                if len(current_ids) == 1:
                    await self.db.delete(ur)
                else:
                    ur.role_ids = [rid for rid in current_ids if rid != role.role_id]
                    self.db.add(ur)

        # Delete the role row
        await self.db.delete(role)
        await self.db.commit()

        await cache.delete_pattern(f"permission:{role_name}:*")

        return {
            "deleted": role_name,
            "stage_permissions_deleted": len(stage_perms),
            "form_type_permissions_deleted": len(ft_perms),
            "user_assignments_deleted": users_count,
        }

    async def rename_role(
        self, old_role_name: str, new_role_name: str
    ) -> Dict[str, str]:
        """Rename a role: update roles.role_name (single truth source), then
        propagate to stage/form-type permission rows which still store role_name.
        user_roles rows don't need updating — they store role_id.
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

        # Update form type permissions
        ft_result = await self.db.execute(
            select(FormTypePermission).where(
                FormTypePermission.role_name == old_role_name
            )
        )
        ft_perms = ft_result.scalars().all()
        for perm in ft_perms:
            perm.role_name = new_role_name

        await self.db.commit()
        await cache.delete_pattern(f"permission:{old_role_name}:*")
        await cache.delete_pattern(f"permission:{new_role_name}:*")

        return {
            "renamed": f"{old_role_name} -> {new_role_name}",
            "stage_permissions_updated": len(stage_perms),
            "form_type_permissions_updated": len(ft_perms),
            "user_assignments_updated": 0,  # stored by role_id — no update needed
        }

    # ------------------------------------------------------------------
    # Superadmin Role Seeding
    # ------------------------------------------------------------------

    async def seed_superadmin_role(self) -> None:
        """
        Ensures a 'superadmin' role tracker exists, then grants it full permissions
        on every stage and form-type currently in the database.

        This is idempotent — safe to call on every startup. It upserts permissions
        rather than creating duplicates.
        """
        from src.app.models.form_type import FormType

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
                perm.can_create = True
                perm.can_edit = True
                perm.can_delete = True
                perm.can_submit = True
                perm.can_manage_permissions = True
            else:
                self.db.add(FormTypePermission(
                    form_type_id=ft.form_type_id,
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
        await cache.delete_pattern(f"permission:{ROLE}:*")
        logger.info(f"Seeded '{ROLE}' role with full permissions on {len(stages)} stages and {len(form_types)} form types.")
