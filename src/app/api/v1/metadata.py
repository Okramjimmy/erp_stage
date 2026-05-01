"""Metadata API endpoints."""

from typing import Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.database import get_db
from src.app.services.metadata_service import MetadataService

router = APIRouter(prefix="/metadata", tags=["Metadata"])


@router.get("/master")
async def get_master_metadata(
    force: bool = Query(False, description="Force regenerate from database"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get master metadata tree.

    Master metadata contains the complete hierarchical tree structure
    with all stages and form types.

    Set force=True to regenerate from database.
    """
    service = MetadataService(db)
    return await service.get_master_metadata(force_regenerate=force)


@router.get("/registry")
async def get_metadata_registry(
    force: bool = Query(False, description="Force regenerate from database"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get metadata registry for O(1) lookups.

    Registry provides flat lookup index for stages and form types
    without traversing the tree.
    """
    service = MetadataService(db)
    return await service.get_metadata_registry(force_regenerate=force)


@router.get("/stages/{stage_id}")
async def get_stage_metadata(stage_id: str, db: AsyncSession = Depends(get_db)):
    """Get metadata for a specific stage."""
    service = MetadataService(db)
    metadata = await service.get_stage_metadata(stage_id)
    if not metadata:
        raise HTTPException(status_code=404, detail=f"Stage {stage_id} not found")
    return metadata


@router.post("/regenerate")
async def regenerate_metadata(db: AsyncSession = Depends(get_db)):
    """
    Regenerate all metadata (master tree and registry).

    This should be called after bulk operations or to ensure consistency.
    """
    service = MetadataService(db)
    return await service.regenerate_all_metadata()


@router.get("/validate")
async def validate_metadata(db: AsyncSession = Depends(get_db)):
    """
    Validate metadata consistency.

    Checks:
    - All stages in DB are in registry
    - All form types in DB are in registry
    - Lineage paths are correct
    - Parent-child relationships are valid
    """
    service = MetadataService(db)
    return await service.validate_metadata_consistency()


@router.get("/statistics")
async def get_statistics(db: AsyncSession = Depends(get_db)):
    """Get statistics about the current system state."""
    service = MetadataService(db)
    master_metadata = await service.get_master_metadata()

    return {
        "stages": master_metadata["statistics"],
        "provider": {
            "version": master_metadata["version"],
            "generated_at": master_metadata["generated_at"],
        },
    }
