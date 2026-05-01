import logging
import uuid
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
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

        # Check for path conflicts
        existing = await self.db.execute(
            select(Stage).where(Stage.stage_path == stage_path)
        )
        if existing.scalar_one_or_none():
            raise ValueError(f"Stage path {stage_path} already exists")

        # Create new stage
        new_stage = Stage(
            stage_id=self.generate_stage_id(),
            stage_name=stage_data.stage_name,
            parent_stage_id=stage_data.parent_stage_id,
            stage_path=stage_path,
            depth_level=depth_level,
            lineage_path=lineage_path,
            visibility_scope=stage_data.visibility_scope,
            created_by=created_by,
        )

        self.db.add(new_stage)
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
                    (Stage.lineage_path.contains([root_stage_id]))
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
        query = select(Stage).where(ancestor_stage_id == Stage.lineage_path[any()])

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

        # Check for circular reference
        if target_parent_id in stage.lineage_path:
            raise ValueError("Cannot move stage to its own descendant")

        # Get all descendants
        descendants = await self.get_descendant_stages(stage_id)

        # Calculate new lineage and paths
        old_path = stage.stage_path
        new_path = f"{target_parent.stage_path}/{stage.stage_name}"

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
        if recursive:
            # Get all descendants
            descendants = await self.get_descendant_stages(stage_id)
            stage_ids = [d.stage_id for d in descendants] + [stage_id]
        else:
            stage_ids = [stage_id]

        # Delete stages (cascade will handle form types and permissions)
        for stage_id in stage_ids:
            result = await self.db.execute(
                select(Stage).where(Stage.stage_id == stage_id)
            )
            stage = result.scalar_one_or_none()
            if stage:
                await self.db.delete(stage)

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
