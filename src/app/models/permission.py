from sqlalchemy import BigInteger, Boolean, Integer, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

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

    # Scoping
    location_id = Column(
        String(36), ForeignKey("locations.location_id", ondelete="CASCADE"), nullable=True
    )
    department_id = Column(
        String(36), ForeignKey("departments.department_id", ondelete="CASCADE"), nullable=True
    )

    # Permissions
    can_view = Column(Boolean, nullable=False, default=False)
    can_create = Column(Boolean, nullable=False, default=False)
    can_edit = Column(Boolean, nullable=False, default=False)
    can_delete = Column(Boolean, nullable=False, default=False)
    can_manage_permissions = Column(Boolean, nullable=False, default=False)

    # Timestamps
    granted_by = Column(String(100))
    granted_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    stage = relationship("Stage", back_populates="permissions")
    location = relationship("Location", foreign_keys=[location_id], lazy="selectin")
    department = relationship("Department", foreign_keys=[department_id], lazy="selectin")

    def __repr__(self):
        return f"<StagePermission(stage={self.stage_id}, role={self.role_name}, location={self.location_id}, dept={self.department_id})>"

    def to_dict(self):
        """Convert model to dictionary."""
        return {
            "permission_id": self.permission_id,
            "stage_id": self.stage_id,
            "role_name": self.role_name,
            "location_id": self.location_id,
            "department_id": self.department_id,
            "can_view": self.can_view,
            "can_create": self.can_create,
            "can_edit": self.can_edit,
            "can_delete": self.can_delete,
            "can_manage_permissions": self.can_manage_permissions,
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

    # Scoping
    location_id = Column(
        String(36), ForeignKey("locations.location_id", ondelete="CASCADE"), nullable=True
    )
    department_id = Column(
        String(36), ForeignKey("departments.department_id", ondelete="CASCADE"), nullable=True
    )

    # Permissions
    can_view = Column(Boolean, nullable=False, default=False)
    can_create_records = Column(Boolean, nullable=False, default=False)
    can_edit = Column(Boolean, nullable=False, default=False)
    can_delete = Column(Boolean, nullable=False, default=False)
    can_edit_records = Column(Boolean, nullable=False, default=False)
    can_delete_records = Column(Boolean, nullable=False, default=False)
    can_submit = Column(Boolean, nullable=False, default=False)
    can_verify = Column(Boolean, nullable=False, default=False)
    can_cancel = Column(Boolean, nullable=False, default=False)
    can_amend = Column(Boolean, nullable=False, default=False)
    can_manage_permissions = Column(Boolean, nullable=False, default=False)

    # Timestamps
    granted_by = Column(String(100))
    granted_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    form_type = relationship("FormType", back_populates="permissions")
    location = relationship("Location", foreign_keys=[location_id], lazy="selectin")
    department = relationship("Department", foreign_keys=[department_id], lazy="selectin")

    def __repr__(self):
        return f"<FormTypePermission(form_type={self.form_type_id}, role={self.role_name}, location={self.location_id}, dept={self.department_id})>"

    def to_dict(self):
        """Convert model to dictionary."""
        return {
            "permission_id": self.permission_id,
            "form_type_id": self.form_type_id,
            "role_name": self.role_name,
            "location_id": self.location_id,
            "department_id": self.department_id,
            "can_view": self.can_view,
            "can_create_records": self.can_create_records,
            "can_edit": self.can_edit,
            "can_delete": self.can_delete,
            "can_edit_records": self.can_edit_records,
            "can_delete_records": self.can_delete_records,
            "can_submit": self.can_submit,
            "can_verify": self.can_verify,
            "can_cancel": self.can_cancel,
            "can_amend": self.can_amend,
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


class RoleSet(Base):
    """A reusable, named bundle of roles that a stage can point to.

    Declares which roles are valid to assign at a stage — pure unordered
    membership, no escalation-order semantics (that lives entirely in
    WorkflowAssignment and is unrelated to this).
    """

    __tablename__ = "role_sets"

    role_set_id = Column(String(50), primary_key=True)
    name = Column(String(150), nullable=False, unique=True)
    description = Column(Text, nullable=True)
    created_by = Column(String(100))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    roles = relationship("Role", secondary="role_set_roles", lazy="selectin")

    def __repr__(self):
        return f"<RoleSet(id={self.role_set_id}, name={self.name})>"

    def to_dict(self):
        return {
            "role_set_id": self.role_set_id,
            "name": self.name,
            "description": self.description,
            "role_names": [r.role_name for r in self.roles],
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class RoleSetRole(Base):
    """SQLAlchemy association model for linking RoleSets to Roles."""

    __tablename__ = "role_set_roles"

    role_set_id = Column(
        String(50), ForeignKey("role_sets.role_set_id", ondelete="CASCADE"), primary_key=True
    )
    role_id = Column(
        Integer, ForeignKey("roles.role_id", ondelete="CASCADE"), primary_key=True
    )

    def __repr__(self):
        return f"<RoleSetRole(role_set_id={self.role_set_id}, role_id={self.role_id})>"


class ProjectRole(Base):
    """A project's (depth-1 Stage) Roles roster: which global roles this
    project uses at all. Every stage below the project is restricted to
    these roles when assigning a UserProjectRole. Empty = unrestricted."""

    __tablename__ = "project_roles"

    stage_id = Column(
        String(50), ForeignKey("stages.stage_id", ondelete="CASCADE"), primary_key=True
    )
    role_id = Column(
        Integer, ForeignKey("roles.role_id", ondelete="CASCADE"), primary_key=True
    )

    def __repr__(self):
        return f"<ProjectRole(stage_id={self.stage_id}, role_id={self.role_id})>"


class ProjectMember(Base):
    """A project's (depth-1 Stage) Members roster: which users belong to
    this project's team. Every stage below the project is restricted to
    these users when assigning a UserProjectRole. Empty = unrestricted."""

    __tablename__ = "project_members"

    stage_id = Column(
        String(50), ForeignKey("stages.stage_id", ondelete="CASCADE"), primary_key=True
    )
    user_id = Column(
        String(36), ForeignKey("users.user_id", ondelete="CASCADE"), primary_key=True
    )

    def __repr__(self):
        return f"<ProjectMember(stage_id={self.stage_id}, user_id={self.user_id})>"


class UserProjectRole(Base):
    """
    One row per (user, project/stage, role) assignment.
    stage_id NULL means the role is granted globally (applies to every stage).
    A user can hold many rows: multiple projects, multiple roles per project.
    """

    __tablename__ = "user_project_roles"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(
        String(36),
        ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
    )
    stage_id = Column(
        String(50), ForeignKey("stages.stage_id", ondelete="CASCADE"), nullable=True
    )
    role_id = Column(
        Integer, ForeignKey("roles.role_id", ondelete="CASCADE"), nullable=False
    )
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())
    assigned_by = Column(String(100))

    user = relationship("User", back_populates="roles")
    stage = relationship("Stage", lazy="selectin")
    role = relationship("Role", lazy="selectin")

    def __repr__(self):
        return f"<UserProjectRole(user={self.user_id}, stage={self.stage_id}, role_id={self.role_id})>"

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "stage_id": self.stage_id,
            "role_id": self.role_id,
            "role_name": self.role.role_name if self.role else None,
            "assigned_at": self.assigned_at.isoformat() if self.assigned_at else None,
            "assigned_by": self.assigned_by,
        }


class CategoryPermission(Base):
    """SQLAlchemy model for FormType-category permissions, scoped to a project (stage).

    Sits between StagePermission and FormTypePermission in the resolution chain:
    a role's permission on all form types whose `group` matches `category`, within
    the given stage's subtree.
    """

    __tablename__ = "category_permissions"

    # Primary key
    permission_id = Column(BigInteger, primary_key=True, autoincrement=True)

    # Project (stage) and category
    stage_id = Column(
        String(50), ForeignKey("stages.stage_id", ondelete="CASCADE"), nullable=False
    )
    category = Column(String(100), nullable=False)
    role_name = Column(String(100), nullable=False)

    # Scoping
    location_id = Column(
        String(36), ForeignKey("locations.location_id", ondelete="CASCADE"), nullable=True
    )
    department_id = Column(
        String(36), ForeignKey("departments.department_id", ondelete="CASCADE"), nullable=True
    )

    # Permissions
    can_view = Column(Boolean, nullable=False, default=False)
    can_create_records = Column(Boolean, nullable=False, default=False)
    can_edit = Column(Boolean, nullable=False, default=False)
    can_delete = Column(Boolean, nullable=False, default=False)
    can_edit_records = Column(Boolean, nullable=False, default=False)
    can_delete_records = Column(Boolean, nullable=False, default=False)
    can_submit = Column(Boolean, nullable=False, default=False)
    can_verify = Column(Boolean, nullable=False, default=False)
    can_cancel = Column(Boolean, nullable=False, default=False)
    can_amend = Column(Boolean, nullable=False, default=False)
    can_manage_permissions = Column(Boolean, nullable=False, default=False)

    # Timestamps
    granted_by = Column(String(100))
    granted_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationships
    stage = relationship("Stage", lazy="selectin")
    location = relationship("Location", foreign_keys=[location_id], lazy="selectin")
    department = relationship("Department", foreign_keys=[department_id], lazy="selectin")

    def __repr__(self):
        return f"<CategoryPermission(stage={self.stage_id}, category={self.category}, role={self.role_name})>"

    def to_dict(self):
        """Convert model to dictionary."""
        return {
            "permission_id": self.permission_id,
            "stage_id": self.stage_id,
            "category": self.category,
            "role_name": self.role_name,
            "location_id": self.location_id,
            "department_id": self.department_id,
            "can_view": self.can_view,
            "can_create_records": self.can_create_records,
            "can_edit": self.can_edit,
            "can_delete": self.can_delete,
            "can_edit_records": self.can_edit_records,
            "can_delete_records": self.can_delete_records,
            "can_submit": self.can_submit,
            "can_verify": self.can_verify,
            "can_cancel": self.can_cancel,
            "can_amend": self.can_amend,
            "can_manage_permissions": self.can_manage_permissions,
            "granted_by": self.granted_by,
            "granted_at": self.granted_at.isoformat() if self.granted_at else None,
        }

