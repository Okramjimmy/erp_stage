"""User service — all DB operations for the User model."""

import logging
import uuid
from typing import List, Optional, Tuple

from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.app.models.permission import Role, UserRole
from src.app.models.user import User
from src.app.schemas.user import UserCreate, UserUpdate

logger = logging.getLogger(__name__)

# Argon2id password hashing context
pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


class UserService:
    def __init__(self, db: AsyncSession):
        self.db = db

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def get_by_id(self, user_id: str) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.user_id == user_id))
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.username == username))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.email == email))
        return result.scalar_one_or_none()

    async def get_user_with_roles(self, user_id: str) -> Optional[Tuple[User, List[str]]]:
        """Return (User, [role_names]) by loading the UserRole row and resolving role_ids."""
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.roles))
            .where(User.user_id == user_id)
        )
        user = result.scalar_one_or_none()
        if not user:
            return None
        role_names = await self._resolve_role_ids(user.roles.role_ids if user.roles else [])
        return user, role_names

    async def list_users(self, skip: int = 0, limit: int = 100) -> List[Tuple[User, List[str]]]:
        """Return list of (User, [role_names]) tuples."""
        result = await self.db.execute(
            select(User)
            .options(selectinload(User.roles))
            .offset(skip)
            .limit(limit)
            .order_by(User.created_at.desc())
        )
        users = result.scalars().all()
        out = []
        for u in users:
            role_ids = u.roles.role_ids if u.roles else []
            names = await self._resolve_role_ids(role_ids)
            out.append((u, names))
        return out

    async def _resolve_role_ids(self, role_ids: list) -> List[str]:
        """Convert a list of role_id integers into role_name strings."""
        if not role_ids:
            return []
        result = await self.db.execute(
            select(Role.role_name).where(Role.role_id.in_(role_ids))
        )
        return [r[0] for r in result.all()]

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def create_user(self, data: UserCreate, created_by: str = "system") -> User:
        """Create a new user, validating uniqueness constraints first."""
        # Uniqueness checks
        if await self.get_by_username(data.username):
            raise ValueError(f"Username '{data.username}' is already taken")
        if await self.get_by_email(data.email):
            raise ValueError(f"Email '{data.email}' is already registered")

        user = User(
            user_id=str(uuid.uuid4()),
            username=data.username,
            email=data.email,
            full_name=data.full_name,
            department=data.department,
            phone=data.phone,
            hashed_password=hash_password(data.password),
            is_active=True,
            is_superadmin=data.is_superadmin,
        )
        self.db.add(user)
        await self.db.commit()
        await self.db.refresh(user)
        logger.info(f"Created user {user.username} (id={user.user_id})")
        return user

    async def update_user(self, user_id: str, data: UserUpdate) -> User:
        """Update allowed profile fields."""
        user = await self.get_by_id(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")

        if data.full_name is not None:
            user.full_name = data.full_name
        if data.email is not None:
            existing = await self.get_by_email(data.email)
            if existing and existing.user_id != user_id:
                raise ValueError("Email already in use by another account")
            user.email = data.email
        if data.department is not None:
            user.department = data.department
        if data.phone is not None:
            user.phone = data.phone

        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def update_photo_key(self, user_id: str, minio_key: str) -> User:
        """Set profile_photo_url to the MinIO object key after a successful upload."""
        user = await self.get_by_id(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        user.profile_photo_url = minio_key
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def change_password(
        self, user_id: str, current_password: str, new_password: str
    ) -> None:
        """Verify current password then update to a new Argon2 hash."""
        user = await self.get_by_id(user_id)
        if not user:
            raise ValueError("User not found")
        if not verify_password(current_password, user.hashed_password):
            raise ValueError("Current password is incorrect")
        user.hashed_password = hash_password(new_password)
        await self.db.commit()

    async def set_active(self, user_id: str, is_active: bool) -> User:
        """Activate or deactivate a user account."""
        user = await self.get_by_id(user_id)
        if not user:
            raise ValueError(f"User {user_id} not found")
        user.is_active = is_active
        await self.db.commit()
        await self.db.refresh(user)
        return user

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def authenticate(self, username_or_email: str, password: str) -> Optional[User]:
        """Return User if credentials are valid and account is active, else None."""
        import re
        if re.search(r"@.*\.", username_or_email):
            user = await self.get_by_email(username_or_email)
        else:
            user = await self.get_by_username(username_or_email)

        if not user:
            return None
        if not user.is_active:
            return None
        if not verify_password(password, user.hashed_password):
            return None
        return user

    # ------------------------------------------------------------------
    # Roles (multi-role support)
    # ------------------------------------------------------------------

    async def get_user_roles(self, user_id: str) -> List[str]:
        """Return all role names for a user by resolving their role_ids array."""
        result = await self.db.execute(
            select(UserRole).where(UserRole.user_id == user_id)
        )
        row = result.scalar_one_or_none()
        return await self._resolve_role_ids(row.role_ids if row and row.role_ids else [])

    async def assign_roles(self, user_id: str, role_names: List[str], assigned_by: str = "system") -> None:
        """Add roles to user's role_ids JSONB array by resolving names → IDs (idempotent)."""
        # Resolve role names to IDs
        if not role_names:
            return
        roles_result = await self.db.execute(
            select(Role).where(Role.role_name.in_(role_names))
        )
        roles = roles_result.scalars().all()
        missing = set(role_names) - {r.role_name for r in roles}
        if missing:
            logger.warning(f"assign_roles: roles not found: {missing}, skipping")
        if not roles:
            return

        result = await self.db.execute(
            select(UserRole).where(UserRole.user_id == user_id)
        )
        row = result.scalar_one_or_none()
        new_ids = {r.role_id for r in roles}

        if row:
            existing = set(row.role_ids or [])
            row.role_ids = sorted(existing | new_ids)
            row.assigned_by = assigned_by
        else:
            self.db.add(UserRole(
                user_id=user_id,
                role_ids=sorted(new_ids),
                assigned_by=assigned_by,
            ))
        await self.db.commit()

    async def revoke_role(self, user_id: str, role_name: str) -> None:
        """Remove a role from the user's role_ids JSONB array."""
        role_result = await self.db.execute(
            select(Role).where(Role.role_name == role_name)
        )
        role = role_result.scalar_one_or_none()
        if not role:
            return
        result = await self.db.execute(
            select(UserRole).where(UserRole.user_id == user_id)
        )
        row = result.scalar_one_or_none()
        if row and role.role_id in (row.role_ids or []):
            row.role_ids = [rid for rid in row.role_ids if rid != role.role_id]
            await self.db.commit()

    # ------------------------------------------------------------------
    # Seeding
    # ------------------------------------------------------------------

    async def seed_superadmin(self) -> None:
        """
        Called at app startup. Creates a default superadmin user if the
        users table is empty. Ensures the 'superadmin' role exists and is
        assigned to the seeded admin via role_ids JSONB array.
        """
        result = await self.db.execute(select(User).limit(1))
        if result.scalar_one_or_none() is not None:
            return  # users already exist

        logger.warning(
            "No users found — seeding default superadmin. "
            "Login: admin / changeme123  (change immediately!)"
        )

        # Get or create the 'superadmin' role to obtain its role_id
        role_result = await self.db.execute(
            select(Role).where(Role.role_name == "superadmin")
        )
        superadmin_role = role_result.scalar_one_or_none()
        if not superadmin_role:
            superadmin_role = Role(
                role_name="superadmin",
                description="Full system access",
                created_by="system",
            )
            self.db.add(superadmin_role)
            await self.db.flush()  # flush to get role_id before using it

        admin_id = str(uuid.uuid4())
        admin = User(
            user_id=admin_id,
            username="admin",
            email="admin@erp.local",
            full_name="System Administrator",
            department="IT",
            hashed_password=hash_password("changeme123"),
            is_active=True,
            is_superadmin=True,
        )
        self.db.add(admin)
        self.db.add(UserRole(
            user_id=admin_id,
            role_ids=[superadmin_role.role_id],
            assigned_by="system",
        ))
        await self.db.commit()
        logger.info("Default superadmin user created and assigned 'superadmin' role.")
