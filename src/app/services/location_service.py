"""Location service — DB operations for the Location model."""

import logging
import uuid
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.app.models.location import Location
from src.app.schemas.location import LocationCreate, LocationUpdate

logger = logging.getLogger(__name__)


class LocationService:
    """Service to manage locations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_by_id(self, location_id: str) -> Optional[Location]:
        """Get location by its ID."""
        result = await self.db.execute(
            select(Location).where(Location.location_id == location_id)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[Location]:
        """Get location by its name."""
        result = await self.db.execute(
            select(Location).where(Location.name == name)
        )
        return result.scalar_one_or_none()

    async def get_or_create(self, name: str) -> Location:
        """Get location by name or create a new one if it doesn't exist."""
        loc = await self.get_by_name(name)
        if not loc:
            loc = Location(
                location_id=str(uuid.uuid4()),
                name=name,
            )
            self.db.add(loc)
            await self.db.commit()
            await self.db.refresh(loc)
            logger.info(f"Created new location: {name} (id={loc.location_id})")
        return loc

    async def list_locations(self, skip: int = 0, limit: int = 100) -> List[Location]:
        """List all locations."""
        result = await self.db.execute(
            select(Location).offset(skip).limit(limit).order_by(Location.name.asc())
        )
        return list(result.scalars().all())

    async def create(self, data: LocationCreate) -> Location:
        """Create a new location."""
        existing = await self.get_by_name(data.name)
        if existing:
            raise ValueError(f"Location '{data.name}' already exists")
        loc = Location(
            location_id=str(uuid.uuid4()),
            name=data.name,
            description=data.description,
        )
        self.db.add(loc)
        await self.db.commit()
        await self.db.refresh(loc)
        logger.info(f"Created location: {loc.name} (id={loc.location_id})")
        return loc

    async def update(self, location_id: str, data: LocationUpdate) -> Location:
        """Update a location's details."""
        loc = await self.get_by_id(location_id)
        if not loc:
            raise ValueError("Location not found")
        if data.name is not None:
            existing = await self.get_by_name(data.name)
            if existing and existing.location_id != location_id:
                raise ValueError("Location name already in use")
            loc.name = data.name
        if data.description is not None:
            loc.description = data.description
        await self.db.commit()
        await self.db.refresh(loc)
        logger.info(f"Updated location: {loc.name} (id={loc.location_id})")
        return loc

    async def delete(self, location_id: str) -> None:
        """Delete a location."""
        loc = await self.get_by_id(location_id)
        if not loc:
            raise ValueError("Location not found")
        await self.db.delete(loc)
        await self.db.commit()
        logger.info(f"Deleted location: {loc.name} (id={location_id})")
