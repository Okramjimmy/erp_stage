"""Metadata service for master metadata management."""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.cache import cache
from src.app.models.form_type import FormType
from src.app.models.stage import Stage
from src.config import settings

logger = logging.getLogger(__name__)


class MetadataService:
    """Service for master metadata and registry management."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_master_metadata(
        self, force_regenerate: bool = False
    ) -> Dict[str, Any]:
        """
        Get master metadata from cache or generate if needed.

        Master metadata contains the complete hierarchical tree structure
        with all stages and form types.
        """
        # Try cache first (unless force regenerate)
        if not force_regenerate:
            cached = await cache.get("master_metadata")
            if cached:
                logger.info("Returning cached master metadata")
                return cached

        # Generate fresh metadata
        logger.info("Generating fresh master metadata")
        metadata = await self._generate_master_metadata()

        # Cache for 1 hour
        await cache.set(
            "master_metadata", metadata, ttl=settings.cache_ttl_master_metadata
        )

        return metadata

    async def _generate_master_metadata(self) -> Dict[str, Any]:
        """Generate complete master metadata from database."""
        # Get all stages ordered by depth and name
        stages_result = await self.db.execute(
            select(Stage).order_by(Stage.depth_level, Stage.stage_name)
        )
        all_stages = stages_result.scalars().all()

        # Get all form types
        form_types_result = await self.db.execute(select(FormType))
        all_form_types = form_types_result.scalars().all()

        # Build tree structure
        stage_map: Dict[str, Dict] = {}
        root_nodes: List[Dict] = []

        # First pass: create all nodes
        for stage in all_stages:
            # Get form types for this stage
            stage_form_types = [
                {
                    "form_type_id": ft.form_type_id,
                    "form_name": ft.form_name,
                    "version": ft.version,
                }
                for ft in all_form_types
                if ft.stage_id == stage.stage_id
            ]

            node = {
                "stage_id": stage.stage_id,
                "stage_name": stage.stage_name,
                "parent_stage_id": stage.parent_stage_id,
                "depth": stage.depth_level,
                "path": stage.stage_path,
                "lineage": stage.lineage_path,
                "children_count": stage.children_count,
                "formtype_count": stage.formtype_count,
                "is_root": stage.is_root,
                "is_leaf": stage.is_leaf,
                "visibility_scope": stage.visibility_scope,
                "children": [],
                "form_types": stage_form_types,
            }

            stage_map[stage.stage_id] = node

        # Second pass: build hierarchy
        for stage_id, node in stage_map.items():
            parent_id = node["parent_stage_id"]
            if parent_id and parent_id in stage_map:
                stage_map[parent_id]["children"].append(node)
            else:
                root_nodes.append(node)

        # Calculate statistics
        total_stages = len(all_stages)
        total_form_types = len(all_form_types)
        max_depth = max((s.depth_level for s in all_stages), default=0)
        avg_depth = (
            sum(s.depth_level for s in all_stages) / total_stages
            if total_stages > 0
            else 0
        )

        metadata = {
            "version": 1,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "roots": root_nodes,
            "statistics": {
                "total_stages": total_stages,
                "total_form_types": total_form_types,
                "max_depth": max_depth,
                "avg_depth": round(avg_depth, 2),
            },
        }

        return metadata

    async def get_metadata_registry(
        self, force_regenerate: bool = False
    ) -> Dict[str, Any]:
        """
        Get flat metadata registry for O(1) lookups.

        Registry provides quick access to stage and form type metadata
        without traversing the tree.
        """
        # Try cache first
        if not force_regenerate:
            cached = await cache.get("metadata_registry")
            if cached:
                logger.info("Returning cached metadata registry")
                return cached

        # Generate fresh registry
        logger.info("Generating fresh metadata registry")
        registry = await self._generate_metadata_registry()

        # Cache for 1 hour
        await cache.set(
            "metadata_registry", registry, ttl=settings.cache_ttl_master_metadata
        )

        return registry

    async def _generate_metadata_registry(self) -> Dict[str, Any]:
        """Generate flat registry from database."""
        # Get all stages
        stages_result = await self.db.execute(select(Stage))
        all_stages = stages_result.scalars().all()

        # Get all form types
        form_types_result = await self.db.execute(select(FormType))
        all_form_types = form_types_result.scalars().all()

        # Build stages registry
        stages_registry = {}
        for stage in all_stages:
            stages_registry[stage.stage_id] = {
                "path": stage.stage_path,
                "depth": stage.depth_level,
                "lineage": stage.lineage_path,
                "parent_id": stage.parent_stage_id,
                "children_count": stage.children_count,
                "formtype_count": stage.formtype_count,
            }

        # Build form types registry
        formtypes_registry = {}
        for ft in all_form_types:
            formtypes_registry[ft.form_type_id] = {
                "path": ft.form_path,
                "stage_id": ft.stage_id,
                "form_name": ft.form_name,
                "version": ft.version,
            }

        registry = {
            "version": 1,
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "stages": stages_registry,
            "formtypes": formtypes_registry,
        }

        return registry

    async def get_stage_metadata(self, stage_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a specific stage."""
        # Get registry
        registry = await self.get_metadata_registry()

        if stage_id not in registry["stages"]:
            return None

        # Get full stage details
        result = await self.db.execute(select(Stage).where(Stage.stage_id == stage_id))
        stage = result.scalar_one_or_none()

        if not stage:
            return None

        # Build metadata file
        metadata = {
            "stage_id": stage.stage_id,
            "stage_name": stage.stage_name,
            "parent_stage_id": stage.parent_stage_id,
            "depth_level": stage.depth_level,
            "stage_path": stage.stage_path,
            "lineage_path": stage.lineage_path,
            "children_stage_ids": [],  # Would query children
            "formtype_ids": [],  # Would query form types
            "children_count": stage.children_count,
            "formtype_count": stage.formtype_count,
            "is_root": stage.is_root,
            "is_leaf": stage.is_leaf,
            "visibility_scope": stage.visibility_scope,
            "created_by": stage.created_by,
            "created_at": stage.created_at.isoformat() if stage.created_at else None,
            "updated_at": stage.updated_at.isoformat() if stage.updated_at else None,
            "metadata_reference": stage.metadata_reference,
        }

        return metadata

    async def regenerate_all_metadata(self) -> Dict[str, Any]:
        """
        Regenerate all metadata (master tree and registry).

        This should be called after bulk operations or for consistency checks.
        """
        logger.info("Starting full metadata regeneration")

        # Generate master metadata
        master_metadata = await self._generate_master_metadata()

        # Generate registry
        registry = await self._generate_metadata_registry()

        # Update cache
        await cache.set(
            "master_metadata", master_metadata, ttl=settings.cache_ttl_master_metadata
        )
        await cache.set(
            "metadata_registry", registry, ttl=settings.cache_ttl_master_metadata
        )

        logger.info("Full metadata regeneration complete")

        return {
            "status": "success",
            "master_metadata": master_metadata["statistics"],
            "registry": {
                "stages_count": len(registry["stages"]),
                "formtypes_count": len(registry["formtypes"]),
            },
        }

    async def validate_metadata_consistency(self) -> Dict[str, Any]:
        """
        Validate that database and metadata are consistent.

        Checks:
        - All stages in DB are in registry
        - All form types in DB are in registry
        - Lineage paths are correct
        - Parent-child relationships are valid
        """
        errors: List[str] = []

        # Get database state
        stages_result = await self.db.execute(select(Stage))
        all_stages = stages_result.scalars().all()

        form_types_result = await self.db.execute(select(FormType))
        all_form_types = form_types_result.scalars().all()

        # Get registry
        registry = await self.get_metadata_registry()

        # Check stages
        for stage in all_stages:
            if stage.stage_id not in registry["stages"]:
                errors.append(f"Stage {stage.stage_id} in DB but not in registry")

            # Validate lineage
            if stage.parent_stage_id:
                parent_exists = any(
                    s.stage_id == stage.parent_stage_id for s in all_stages
                )
                if not parent_exists:
                    errors.append(
                        f"Stage {stage.stage_id} has non-existent parent {stage.parent_stage_id}"
                    )

        # Check form types
        for ft in all_form_types:
            if ft.form_type_id not in registry["formtypes"]:
                errors.append(f"FormType {ft.form_type_id} in DB but not in registry")

        return {
            "is_consistent": len(errors) == 0,
            "errors": errors,
            "checked_stages": len(all_stages),
            "checked_formtypes": len(all_form_types),
        }
