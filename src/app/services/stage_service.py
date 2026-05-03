import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.app.cache import cache
from src.app.models.form_type import FormType
from src.app.models.stage import Stage
from src.app.schemas.stage import (
    FormTypeRef,
    StageCreate,
    StageMoveResponse,
    StageResponse,
    StageTreeNode,
    StageUpdate,
)
from src.config import settings

logger = logging.getLogger(__name__)


class StageService:
    """Service for Stage operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def generate_stage_id(prefix: str = "stage") -> str:
        """Generate unique stage ID."""
        return f"{prefix}_{uuid.uuid4().hex[:12]}"

    async def create_stage(
        self, stage_data: StageCreate, created_by: Optional[str] = None
    ) -> StageResponse:
        """Create a new stage with hierarchical metadata."""
        # Validate parent exists if provided
        parent_stage = None
        lineage_path: List[str] = []
        depth_level = 0
        stage_path = "/"

        if stage_data.parent_stage_id:
            # Fetch parent stage
            result = await self.db.execute(
                select(Stage).where(Stage.stage_id == stage_data.parent_stage_id)
            )
            parent_stage = result.scalar_one_or_none()

            if not parent_stage:
                raise ValueError(f"Parent stage {stage_data.parent_stage_id} not found")

            # Calculate hierarchy metadata
            lineage_path = parent_stage.lineage_path + [parent_stage.stage_id]
            depth_level = parent_stage.depth_level + 1
            stage_path = f"{parent_stage.stage_path}/{stage_data.stage_name}"

        # Check for path conflicts - this also handles root stage creation
        existing = await self.db.execute(
            select(Stage).where(Stage.stage_path == stage_path)
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Stage path '{stage_path}' already exists. A stage with the name '{stage_data.stage_name}' already exists at this location in the hierarchy.")

        # Additional validation: Check if stage_name would conflict at the root level
        if not parent_stage:
            # For root stages, ensure we're not creating a duplicate root-level name
            root_path_conflict = await self.db.execute(
                select(Stage).where(
                    Stage.stage_path == f"/{stage_data.stage_name}")
            )
            if root_path_conflict.scalar_one_or_none():
                raise ValueError(f"A root-level stage named '{stage_data.stage_name}' already exists. Root-stage names must be unique.")

        # Determine root/leaf status
        is_root = parent_stage is None
        is_leaf = True  # New stages start as leaf nodes

        # Create new stage
        new_stage = Stage(
            stage_id=self.generate_stage_id(),
            stage_name=stage_data.stage_name,
            parent_stage_id=stage_data.parent_stage_id,
            stage_path=stage_path,
            depth_level=depth_level,
            lineage_path=lineage_path,
            visibility_scope=stage_data.visibility_scope,
            is_root=is_root,
            is_leaf=is_leaf,
            created_by=created_by,
        )

        self.db.add(new_stage)

        # If this is a child stage, update parent's state
        if parent_stage:
            parent_stage.is_root = True  # Set parent as root if it has children
            parent_stage.is_leaf = False  # Parent is no longer a leaf
            parent_stage.children_count += 1

        await self.db.commit()
        await self.db.refresh(new_stage)

        # Invalidate caches
        await cache.invalidate_master_metadata()
        await cache.invalidate_stage_cache(new_stage.stage_id)

        return StageResponse.model_validate(new_stage)

    async def get_stage(self, stage_id: str) -> Optional[StageResponse]:
        """Get stage by ID."""
        result = await self.db.execute(select(Stage).where(Stage.stage_id == stage_id))
        stage = result.scalar_one_or_none()

        if not stage:
            return None

        return StageResponse.model_validate(stage)

    async def update_stage(
        self, stage_id: str, stage_data: StageUpdate
    ) -> StageResponse:
        """Update stage name and/or visibility."""
        result = await self.db.execute(
            select(Stage).where(Stage.stage_id == stage_id)
        )
        stage = result.scalar_one_or_none()
        if not stage:
            raise ValueError(f"Stage {stage_id} not found")

        if stage_data.stage_name and stage_data.stage_name != stage.stage_name:
            parent_path = "/".join(stage.stage_path.split("/")[:-1]) or "/"
            new_path = f"{parent_path}/{stage_data.stage_name}".replace("//", "/")
            existing = await self.db.execute(
                select(Stage).where(Stage.stage_path == new_path)
            )
            if existing.scalar_one_or_none():
                raise ValueError(f"Stage path {new_path} already exists")
            stage.stage_path = new_path
            stage.stage_name = stage_data.stage_name

        if stage_data.visibility_scope:
            stage.visibility_scope = stage_data.visibility_scope

        await self.db.commit()
        await self.db.refresh(stage)
        await cache.invalidate_stage_cache(stage_id)

        return StageResponse.model_validate(stage)

    async def get_all_stages(
        self, skip: int = 0, limit: int = 100
    ) -> List[StageResponse]:
        """Get all stages with pagination."""
        result = await self.db.execute(
            select(Stage)
            .order_by(Stage.depth_level, Stage.stage_name)
            .offset(skip)
            .limit(limit)
        )
        stages = result.scalars().all()
        return [StageResponse.model_validate(s) for s in stages]

    async def search_stages(
        self, query: str, limit: int = 50
    ) -> List[StageResponse]:
        """Search stages by name."""
        result = await self.db.execute(
            select(Stage)
            .where(Stage.stage_name.ilike(f"%{query}%"))
            .order_by(Stage.stage_name)
            .limit(limit)
        )
        stages = result.scalars().all()
        return [StageResponse.model_validate(s) for s in stages]

    async def get_stage_tree(
        self, root_stage_id: Optional[str] = None, max_depth: Optional[int] = None
    ) -> List[StageTreeNode]:
        """Get hierarchical stage tree."""
        query = select(Stage).order_by(Stage.depth_level, Stage.stage_name)

        if root_stage_id:
            # Get descendants using lineage
            result = await self.db.execute(
                select(Stage).where(Stage.stage_id == root_stage_id)
            )
            root = result.scalar_one_or_none()

            if not root:
                raise ValueError(f"Root stage {root_stage_id} not found")

            # Get all descendants
            descendants_result = await self.db.execute(
                select(Stage)
                .where(
                    (text(":root_id = ANY(lineage_path)").bindparams(root_id=root_stage_id))
                    | (Stage.stage_id == root_stage_id)
                )
                .order_by(Stage.depth_level, Stage.stage_name)
            )
            stages = descendants_result.scalars().all()
        else:
            stages_result = await self.db.execute(query)
            stages = stages_result.scalars().all()

        # Build tree structure
        stage_map: Dict[str, StageTreeNode] = {}
        root_nodes: List[StageTreeNode] = []

        for stage in stages:
            # Get form types for this stage
            form_types_result = await self.db.execute(
                select(FormType).where(FormType.stage_id == stage.stage_id)
            )
            form_types = form_types_result.scalars().all()

            # Create tree node
            node = StageTreeNode(
                stage_id=stage.stage_id,
                stage_name=stage.stage_name,
                parent_stage_id=stage.parent_stage_id,
                stage_path=stage.stage_path,
                depth_level=stage.depth_level,
                lineage_path=stage.lineage_path,
                children_count=stage.children_count,
                formtype_count=stage.formtype_count,
                is_root=stage.is_root,
                is_leaf=stage.is_leaf,
                visibility_scope=stage.visibility_scope,
                created_by=stage.created_by,
                created_at=stage.created_at,
                updated_at=stage.updated_at,
                metadata_reference=stage.metadata_reference,
                children=[],
                form_types=[
                    FormTypeRef(
                        form_type_id=ft.form_type_id,
                        form_name=ft.form_name,
                        version=ft.version,
                    )
                    for ft in form_types
                ],
            )

            stage_map[stage.stage_id] = node

            if max_depth is None or stage.depth_level <= max_depth:
                if stage.parent_stage_id and stage.parent_stage_id in stage_map:
                    stage_map[stage.parent_stage_id].children.append(node)
                else:
                    root_nodes.append(node)

        # If root_id specified, return only that subtree
        if root_stage_id:
            return [stage_map[root_stage_id]]

        return root_nodes

    async def get_descendant_stages(
        self, ancestor_stage_id: str, max_depth: Optional[int] = None
    ) -> List[StageResponse]:
        """Get all descendant stages using lineage."""
        # Use PostgreSQL's array containment operator
        query = select(Stage).where(
            text(":ancestor_id = ANY(lineage_path)"
        ).bindparams(ancestor_id=ancestor_stage_id)
        )

        if max_depth is not None:
            query = query.where(Stage.depth_level <= max_depth)

        result = await self.db.execute(
            query.order_by(Stage.depth_level, Stage.stage_name)
        )
        stages = result.scalars().all()

        return [StageResponse.model_validate(stage) for stage in stages]

    async def move_stage(
        self, stage_id: str, target_parent_id: str, user_id: Optional[str] = None
    ) -> StageMoveResponse:
        """Move stage with all descendants to new parent."""
        import time

        start_time = time.time()

        # Get stage to move
        stage_result = await self.db.execute(
            select(Stage).where(Stage.stage_id == stage_id)
        )
        stage = stage_result.scalar_one_or_none()

        if not stage:
            raise ValueError(f"Stage {stage_id} not found")

        # Get target parent
        parent_result = await self.db.execute(
            select(Stage).where(Stage.stage_id == target_parent_id)
        )
        target_parent = parent_result.scalar_one_or_none()

        if not target_parent:
            raise ValueError(f"Target parent {target_parent_id} not found")

        # Check for circular reference - prevent any stage from moving to its own descendant
        if target_parent_id in stage.lineage_path:
            raise ValueError(f"Cannot move stage '{stage.stage_name}' to its own descendant '{target_parent.stage_name}'")

        # NEW: Prevent root stages (depth 0) from moving to their descendants
        # For root stages, we need to check if target_parent is in the root's subtree
        if stage.depth_level == 0:
            # Get all descendants of this root stage
            root_descendants_result = await self.db.execute(
                select(Stage).where(
                    text(":stage_id = ANY(lineage_path)").bindparams(stage_id=stage.stage_id)
                )
            )
            root_descendants = [d.stage_id for d in root_descendants_result.scalars().all()]

            # Check if target parent is a descendant of this root stage
            if target_parent_id in root_descendants:
                raise ValueError(f"Cannot move root stage '{stage.stage_name}' to its descendant '{target_parent.stage_name}'. Root stages cannot be moved within their own subtree.")

            # Also check if the target stage IS one of the root's descendants
            # This shouldn't happen due to the circular reference check above, but let's be safe
            if target_parent_id == stage.stage_id:
                raise ValueError(f"Cannot move stage to itself")

        # Store old parent info
        old_parent_id = stage.parent_stage_id

        # Get all descendants
        descendants = await self.get_descendant_stages(stage_id)

        # Calculate new lineage and paths
        old_path = stage.stage_path
        new_path = f"{target_parent.stage_path}/{stage.stage_name}"

        # Update old parent's state (decrement children count)
        if old_parent_id:
            old_parent_result = await self.db.execute(
                select(Stage).where(Stage.stage_id == old_parent_id)
            )
            old_parent = old_parent_result.scalar_one_or_none()
            if old_parent:
                old_parent.children_count -= 1
                old_parent.is_leaf = (old_parent.children_count == 0)

        # Update new parent's state (increment children count)
        target_parent.children_count += 1
        target_parent.is_leaf = False
        target_parent.is_root = True  # Target parent becomes a root node

        # Update stage
        stage.parent_stage_id = target_parent_id
        stage.stage_path = new_path
        stage.depth_level = target_parent.depth_level + 1
        stage.lineage_path = target_parent.lineage_path + [stage.stage_id]

        # Update descendants
        for descendant in descendants:
            # Calculate new lineage
            idx = descendant.lineage_path.index(stage_id)
            new_lineage = (
                target_parent.lineage_path
                + [stage_id]
                + descendant.lineage_path[idx + 1 :]
            )
            descendant.lineage_path = new_lineage

            # Calculate new path
            new_descendant_path = descendant.stage_path.replace(old_path, new_path)
            descendant.stage_path = new_descendant_path

            # Update depth
            descendant.depth_level = (
                target_parent.depth_level
                + 1
                + descendant.depth_level
                - stage.depth_level
            )

        # Update form type paths
        affected_form_types = await self._update_form_type_paths(
            old_path, new_path, [stage_id] + [d.stage_id for d in descendants]
        )

        await self.db.commit()

        # Invalidate caches
        await cache.invalidate_master_metadata()
        await cache.invalidate_stage_cache(stage_id)
        await cache.invalidate_stage_cache(target_parent_id)
        if old_parent_id:
            await cache.invalidate_stage_cache(old_parent_id)

        duration_ms = (time.time() - start_time) * 1000

        return StageMoveResponse(
            stage_id=stage_id,
            old_path=old_path,
            new_path=new_path,
            affected_stages_count=len(descendants) + 1,
            affected_formtypes_count=affected_form_types,
            operation_duration_ms=duration_ms,
        )

    async def _update_form_type_paths(
        self, old_path: str, new_path: str, stage_ids: List[str]
    ) -> int:
        """Update form type paths for moved stages."""
        result = await self.db.execute(
            select(FormType).where(FormType.stage_id.in_(stage_ids))
        )
        form_types = result.scalars().all()

        for form_type in form_types:
            form_type.form_path = form_type.form_path.replace(old_path, new_path)

        return len(form_types)

    async def delete_stage(
        self, stage_id: str, recursive: bool = False
    ) -> Dict[str, int]:
        """Delete stage and optionally all descendants."""
        # Get stage to delete
        stage_result = await self.db.execute(
            select(Stage).where(Stage.stage_id == stage_id)
        )
        stage = stage_result.scalar_one_or_none()

        if not stage:
            raise ValueError(f"Stage {stage_id} not found")

        # Store parent info for later update
        parent_id = stage.parent_stage_id

        if recursive:
            # Get all descendants
            descendants = await self.get_descendant_stages(stage_id)
            stage_ids = [d.stage_id for d in descendants] + [stage_id]
        else:
            stage_ids = [stage_id]

        # Delete stages (cascade will handle form types and permissions)
        for sid in stage_ids:
            result = await self.db.execute(
                select(Stage).where(Stage.stage_id == sid)
            )
            s = result.scalar_one_or_none()
            if s:
                await self.db.delete(s)

        # Update parent's state if stage had a parent
        if parent_id:
            parent_result = await self.db.execute(
                select(Stage).where(Stage.stage_id == parent_id)
            )
            parent = parent_result.scalar_one_or_none()
            if parent:
                # Check if parent still has remaining children
                remaining_children_result = await self.db.execute(
                    select(func.count(Stage.stage_id)).where(
                        Stage.parent_stage_id == parent_id
                    )
                )
                remaining_count = remaining_children_result.scalar()

                parent.children_count = remaining_count
                parent.is_leaf = (remaining_count == 0)
                # Keep is_root = True as parent was already a root node

        await self.db.commit()

        # Invalidate caches
        for sid in stage_ids:
            await cache.invalidate_stage_cache(sid)
        await cache.invalidate_master_metadata()

        return {"deleted_stage_id": stage_id, "deleted_count": len(stage_ids)}

    async def get_all_stages(
        self, skip: int = 0, limit: int = 100
    ) -> List[StageResponse]:
        """Get all stages with pagination."""
        result = await self.db.execute(
            select(Stage)
            .order_by(Stage.depth_level, Stage.stage_name)
            .offset(skip)
            .limit(limit)
        )
        stages = result.scalars().all()

        return [StageResponse.model_validate(stage) for stage in stages]

    async def search_stages(self, query: str, limit: int = 50) -> List[StageResponse]:
        """Search stages by name."""
        result = await self.db.execute(
            select(Stage)
            .where(Stage.stage_name.ilike(f"%{query}%"))
            .order_by(Stage.stage_name)
            .limit(limit)
        )
        stages = result.scalars().all()

        return [StageResponse.model_validate(stage) for stage in stages]
