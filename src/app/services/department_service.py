"""Department service — DB operations for the Department model."""

import logging
import uuid
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.app.models.department import Department
from src.app.schemas.department import DepartmentCreate, DepartmentUpdate

logger = logging.getLogger(__name__)


class DepartmentService:
    """Service to manage departments."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, department_id: str) -> Optional[Department]:
        """Get department by its ID."""
        result = await self.db.execute(
            select(Department).where(Department.department_id == department_id)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[Department]:
        """Get department by its name (case-insensitive)."""
        result = await self.db.execute(
            select(Department).where(Department.name == name)
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, name: str) -> Department:
        """Get department by name or create a new one if it doesn't exist."""
        dept = await self.get_by_name(name)
        if not dept:
            dept = Department(
                department_id=str(uuid.uuid4()),
                name=name,
            )
            self.db.add(dept)
            await self.db.commit()
            await self.db.refresh(dept)
            logger.info(f"Created new department: {name} (id={dept.department_id})")
        return dept

    async def list_departments(self, skip: int = 0, limit: int = 100) -> List[Department]:
        """List all departments."""
        result = await self.db.execute(
            select(Department).offset(skip).limit(limit).order_by(Department.name.asc())
        )
        return list(result.scalars().all())

    async def create(self, data: DepartmentCreate) -> Department:
        """Create a new department."""
        existing = await self.get_by_name(data.name)
        if existing:
            raise ValueError(f"Department '{data.name}' already exists")
        dept = Department(
            department_id=str(uuid.uuid4()),
            name=data.name,
            description=data.description,
        )
        self.db.add(dept)
        await self.db.commit()
        await self.db.refresh(dept)
        logger.info(f"Created department: {dept.name} (id={dept.department_id})")
        return dept

    async def update(self, department_id: str, data: DepartmentUpdate) -> Department:
        """Update a department's details."""
        dept = await self.get_by_id(department_id)
        if not dept:
            raise ValueError("Department not found")
        if data.name is not None:
            existing = await self.get_by_name(data.name)
            if existing and existing.department_id != department_id:
                raise ValueError("Department name already in use")
            dept.name = data.name
        if data.description is not None:
            dept.description = data.description
        await self.db.commit()
        await self.db.refresh(dept)
        logger.info(f"Updated department: {dept.name} (id={dept.department_id})")
        return dept

    async def delete(self, department_id: str) -> None:
        """Delete a department."""
        dept = await self.get_by_id(department_id)
        if not dept:
            raise ValueError("Department not found")
        await self.db.delete(dept)
        await self.db.commit()
        logger.info(f"Deleted department: {dept.name} (id={department_id})")
