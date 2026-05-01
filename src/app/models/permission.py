from sqlalchemy import BigInteger, Boolean, Column, DateTime, ForeignKey, String
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


class UserRole(Base):
    """SQLAlchemy model for User to Role mapping."""

    __tablename__ = "user_roles"

    # Composite primary key
    user_id = Column(String(100), primary_key=True)
    role_name = Column(String(100), primary_key=True)

    # Timestamps
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())
    assigned_by = Column(String(100))

    def __repr__(self):
        return f"<UserRole(user={self.user_id}, role={self.role_name})>"

    def to_dict(self):
        """Convert model to dictionary."""
        return {
            "user_id": self.user_id,
            "role_name": self.role_name,
            "assigned_at": self.assigned_at.isoformat() if self.assigned_at else None,
            "assigned_by": self.assigned_by,
        }
