from sqlalchemy import BigInteger, Boolean, Integer, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB

from src.app.database import Base


class StagePermission(Base):
    """SQLAlchemy model for Stage permissions."""

    __tablename__ = "stage_permissions"

    # Primary key
    permission_id = Column(BigInteger, primary_key=True, autoincrement=True)

    # Stage and Role
    stage_id = Column(
        String(50), ForeignKey("stages.stage_id", ondelete="CASCADE"), nullable=False
    )
    role_name = Column(String(100), nullable=False)

    # Permissions
    can_view = Column(Boolean, nullable=False, default=False)
    can_create = Column(Boolean, nullable=False, default=False)
    can_edit = Column(Boolean, nullable=False, default=False)
    can_delete = Column(Boolean, nullable=False, default=False)
    can_manage_permissions = Column(Boolean, nullable=False, default=False)
    can_submit = Column(Boolean, nullable=False, default=False)

    # Timestamps
    granted_by = Column(String(100))
    granted_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    stage = relationship("Stage", back_populates="permissions")

    def __repr__(self):
        return f"<StagePermission(stage={self.stage_id}, role={self.role_name})>"

    def to_dict(self):
        """Convert model to dictionary."""
        return {
            "permission_id": self.permission_id,
            "stage_id": self.stage_id,
            "role_name": self.role_name,
            "can_view": self.can_view,
            "can_create": self.can_create,
            "can_edit": self.can_edit,
            "can_delete": self.can_delete,
            "can_manage_permissions": self.can_manage_permissions,
            "can_submit": self.can_submit,
            "granted_by": self.granted_by,
            "granted_at": self.granted_at.isoformat() if self.granted_at else None,
        }


class FormTypePermission(Base):
    """SQLAlchemy model for Form Type permissions."""

    __tablename__ = "form_type_permissions"

    # Primary key
    permission_id = Column(BigInteger, primary_key=True, autoincrement=True)

    # Form Type and Role
    form_type_id = Column(
        String(50),
        ForeignKey("form_types.form_type_id", ondelete="CASCADE"),
        nullable=False,
    )
    role_name = Column(String(100), nullable=False)

    # Permissions
    can_view = Column(Boolean, nullable=False, default=False)
    can_create = Column(Boolean, nullable=False, default=False)
    can_edit = Column(Boolean, nullable=False, default=False)
    can_delete = Column(Boolean, nullable=False, default=False)
    can_submit = Column(Boolean, nullable=False, default=False)
    can_manage_permissions = Column(Boolean, nullable=False, default=False)

    # Timestamps
    granted_by = Column(String(100))
    granted_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    form_type = relationship("FormType", back_populates="permissions")

    def __repr__(self):
        return f"<FormTypePermission(form_type={self.form_type_id}, role={self.role_name})>"

    def to_dict(self):
        """Convert model to dictionary."""
        return {
            "permission_id": self.permission_id,
            "form_type_id": self.form_type_id,
            "role_name": self.role_name,
            "can_view": self.can_view,
            "can_create": self.can_create,
            "can_edit": self.can_edit,
            "can_delete": self.can_delete,
            "can_submit": self.can_submit,
            "can_manage_permissions": self.can_manage_permissions,
            "granted_by": self.granted_by,
            "granted_at": self.granted_at.isoformat() if self.granted_at else None,
        }


class Role(Base):
    """Dedicated roles table — the single source of truth for role names."""

    __tablename__ = "roles"

    role_id = Column(Integer, primary_key=True, autoincrement=True)
    role_name = Column(String(100), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    created_by = Column(String(100))


    def __repr__(self):
        return f"<Role(id={self.role_id}, name={self.role_name})>"

    def to_dict(self):
        return {
            "role_id": self.role_id,
            "role_name": self.role_name,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "created_by": self.created_by,
        }


class UserRole(Base):
    """
    One row per user.
    role_ids is a JSONB array of integer role IDs referencing the roles table.
    e.g. [1, 3, 7]
    """

    __tablename__ = "user_roles"

    user_id = Column(
        String(100),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        primary_key=True,
    )
    role_ids = Column(
        JSONB,
        nullable=False,
        default=list,
        server_default="'[]'::jsonb",
    )
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())
    assigned_by = Column(String(100))

    # Relationship back to User (many UserRole rows per user is no longer the case —
    # the User side declares uselist=False so this is the scalar back-populates)
    user = relationship("User", back_populates="roles")

    def __repr__(self):
        return f"<UserRole(user={self.user_id}, role_ids={self.role_ids})>"

    def to_dict(self):
        return {
            "user_id": self.user_id,
            "role_ids": self.role_ids or [],
            "assigned_at": self.assigned_at.isoformat() if self.assigned_at else None,
            "assigned_by": self.assigned_by,
        }

