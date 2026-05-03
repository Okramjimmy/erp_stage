import logging
import re
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
        self, stage_id: str, target_parent_id: Optional[str] = None, user_id: Optional[str] = None
    ) -> StageMoveResponse:
    
        import time
        start_time = time.time()
    
        # --- helpers ---
        def build_path(parent_path: str, name: str) -> str:
            if not parent_path or parent_path == "/":
                return f"/{name}"
            return f"{parent_path}/{name}"
    
        # --- fetch nodes ---
        stage = await self.db.get(Stage, stage_id)
        if not stage:
            raise ValueError(f"Stage {stage_id} not found")
    
        target_parent = None
        if target_parent_id:
            target_parent = await self.db.get(Stage, target_parent_id)
            if not target_parent:
                raise ValueError(f"Target parent {target_parent_id} not found")
        
            if stage_id == target_parent_id:
                raise ValueError("Cannot move stage to itself")
        
            # --- prevent circular move ---
            if stage_id in target_parent.lineage_path:
                raise ValueError("Cannot move a node into its own descendant")
                
            target_lineage = target_parent.lineage_path
            target_path = target_parent.stage_path
            target_depth = target_parent.depth_level
        else:
            target_lineage = []
            target_path = ""
            target_depth = -1
    
        old_parent_id = stage.parent_stage_id
    
        # --- fetch descendants (IMPORTANT: must be actual Stage models) ---
        descendants_result = await self.db.execute(
            select(Stage).where(
                text(":id = ANY(lineage_path)").bindparams(id=stage_id)
            )
        )
        descendants = descendants_result.scalars().all()
    
        old_path = stage.stage_path
        new_path = build_path(target_path, stage.stage_name)
    
        # --- update stage ---
        stage.parent_stage_id = target_parent_id if target_parent_id else None
        stage.stage_path = new_path
        
        # Lineage is the path OF ancestors, so we append target_parent_id (not stage.stage_id)
        if target_parent_id:
            stage.lineage_path = target_lineage + [target_parent_id]
        else:
            stage.lineage_path = []
            
        # recalculate depth level
        stage.depth_level = len(stage.lineage_path)
    
        # --- update descendants ---
        for d in descendants:
            # update lineage
            idx = d.lineage_path.index(stage_id)
            d.lineage_path = (
                stage.lineage_path
                + [stage_id]
                + d.lineage_path[idx + 1 :]
            )
    
            # SAFE path update (prefix replace only)
            if d.stage_path.startswith(old_path):
                suffix = d.stage_path[len(old_path):]
                d.stage_path = new_path + suffix
    
            # recalculate depth level
            d.depth_level = len(d.lineage_path)
    
        # We must flush the pending changes to the database so the COUNT queries
        # in the recompute function see the newly moved parent_stage_ids.
        await self.db.flush()

        # --- recompute children counts + flags ---
        async def recompute(node_id: Optional[str]):
            if not node_id:
                return
    
            node = await self.db.get(Stage, node_id)
            if not node:
                return
    
            result = await self.db.execute(
                select(func.count(Stage.stage_id)).where(
                    Stage.parent_stage_id == node_id
                )
            )
            count = result.scalar()
    
            node.children_count = count
            node.is_leaf = (count == 0)
            node.is_root = (count > 0) or (node.parent_stage_id is None)
    
        await recompute(old_parent_id)
        if target_parent_id:
            await recompute(target_parent_id)
    
        # --- update moved node flags ---
        await recompute(stage_id)
    
        # --- update form paths ---
        stage_ids = [stage_id] + [d.stage_id for d in descendants]
        affected_form_types = await self._update_form_type_paths(
            old_path, new_path, stage_ids
        )
    
        await self.db.commit()
    
        # --- cache ---
        await cache.invalidate_master_metadata()
        await cache.invalidate_stage_cache(stage_id)
        if target_parent_id:
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

        # Use regex to only replace the prefix of form_path, not all occurrences
        # Escape special regex characters in old_path
        escaped_old_path = re.escape(old_path)
        pattern = re.compile(f'^{escaped_old_path}')

        for form_type in form_types:
            # Replace only the prefix (start of string) of form_path
            form_type.form_path = pattern.sub(new_path, form_type.form_path)

        return len(form_types)

    async def delete_stage(
        self, stage_id: str, recursive: bool = True
    ) -> Dict[str, int]:
        """Delete stage and all descendants recursively."""
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
            descendants = []

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
                logger.info(f"Updated parent {parent_id}: children_count={remaining_count}, is_leaf={parent.is_leaf}")

        await self.db.commit()

        # Invalidate caches
        for sid in stage_ids:
            await cache.invalidate_stage_cache(sid)
        await cache.invalidate_master_metadata()

        return {
            "deleted_stage_id": stage_id,
            "deleted_stage_name": stage.stage_name,
            "deleted_count": len(stage_ids),
            "descendants_count": len(descendants),
            "message": f"Successfully deleted stage '{stage.stage_name}' and {len(descendants)} descendant(s)"
        }
