"""Group service — DB operations for the Group model."""

import logging
import uuid
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.app.models.group import Group
from src.app.models.form_type import FormType
from src.app.schemas.group import GroupCreate, GroupUpdate

logger = logging.getLogger(__name__)


class GroupService:
    """Service to manage groups."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, group_id: str) -> Optional[Group]:
        """Get group by its ID."""
        result = await self.db.execute(
            select(Group).where(Group.id == group_id)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[Group]:
        """Get group by its name."""
        result = await self.db.execute(
            select(Group).where(Group.name == name)
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, name: str) -> Group:
        """Get group by name or create a new one if it doesn't exist."""
        name = name.strip()
        gp = await self.get_by_name(name)
        if not gp:
            gp = Group(
                id=str(uuid.uuid4()),
                name=name,
            )
            self.db.add(gp)
            await self.db.commit()
            await self.db.refresh(gp)
            logger.info(f"Created new group: {name} (id={gp.id})")
        return gp

    async def list_groups(self, skip: int = 0, limit: int = 100) -> List[Group]:
        """List all groups."""
        result = await self.db.execute(
            select(Group).offset(skip).limit(limit).order_by(Group.name.asc())
        )
        return list(result.scalars().all())

    async def create(self, data: GroupCreate) -> Group:
        """Create a new group."""
        name = data.name.strip()
        existing = await self.get_by_name(name)
        if existing:
            raise ValueError(f"Group '{name}' already exists")
        gp = Group(
            id=str(uuid.uuid4()),
            name=name,
        )
        self.db.add(gp)
        await self.db.commit()
        await self.db.refresh(gp)
        logger.info(f"Created group: {gp.name} (id={gp.id})")
        return gp

    async def update(self, group_id: str, data: GroupUpdate) -> Group:
        """Update a group's details."""
        gp = await self.get_by_id(group_id)
        if not gp:
            raise ValueError("Group not found")
        if data.name is not None:
            name = data.name.strip()
            existing = await self.get_by_name(name)
            if existing and existing.id != group_id:
                raise ValueError("Group name already in use")
            old_name = gp.name
            gp.name = name
            
            # Update all FormTypes referencing the old group name
            await self.db.execute(
                FormType.__table__.update()
                .where(FormType.group == old_name)
                .values(group=name)
            )
            
        await self.db.commit()
        await self.db.refresh(gp)
        logger.info(f"Updated group: {gp.name} (id={gp.id})")
        return gp

    async def delete(self, group_id: str) -> None:
        """Delete a group."""
        gp = await self.get_by_id(group_id)
        if not gp:
            raise ValueError("Group not found")
        
        # When a group is deleted, set their FormTypes' group field to NULL
        await self.db.execute(
            FormType.__table__.update()
            .where(FormType.group == gp.name)
            .values(group=None)
        )
        
        await self.db.delete(gp)
        await self.db.commit()
        logger.info(f"Deleted group: {gp.name} (id={group_id})")

    async def seed_groups_from_form_types(self) -> None:
        """Seed the groups table with unique group names from the form_types table."""
        # Query distinct non-null groups from form_types
        result = await self.db.execute(
            select(FormType.group).where(FormType.group.isnot(None)).distinct()
        )
        group_names = [r[0] for r in result.all() if r[0]]
        
        for name in group_names:
            name = name.strip()
            if not name:
                continue
            # Check if group already exists
            gp_result = await self.db.execute(
                select(Group).where(Group.name == name)
            )
            if not gp_result.scalar_one_or_none():
                gp = Group(
                    id=str(uuid.uuid4()),
                    name=name,
                )
                self.db.add(gp)
                logger.info(f"Seeding group: {name} (id={gp.id})")
        
        await self.db.commit()
