import logging
import re
import time
import uuid
import random
import string
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.app.cache import cache
from src.app.models.form_type import FormType
from src.app.models.permission import StagePermission
from src.app.models.stage import Stage
from src.app.schemas.stage import (
    FormTypeRef,
    StageCreate,
    StageMovedNode,
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

    @staticmethod
    def generate_random_prefix() -> str:
        """Generate a random 3-character alphanumeric WBS prefix (lowercase)."""
        return "".join(random.choices(string.ascii_lowercase + string.digits, k=3))

    @staticmethod
    def extract_base_name(stage_name: str, prefix: Optional[str]) -> str:
        """Extract the raw base name of a stage, removing the WBS prefix and outline formatting if present."""
        if not stage_name:
            return ""
        # Match: optional 3-alphanumeric prefix, then outline digits (dots & numbers), then whitespace, then the rest
        match = re.match(r'^(?:[a-zA-Z0-9]{3})?(\d+(?:\.\d+)*)\s+(.*)$', stage_name)
        if match:
            return match.group(2)
        return stage_name

    @staticmethod
    def parse_outline_number(stage_name: str, prefix: Optional[str]) -> Optional[List[int]]:
        """Extract the WBS outline sequence numbers from a stage name as a list of integers."""
        if not stage_name:
            return None
        match = re.match(r'^(?:[a-zA-Z0-9]{3})?(\d+(?:\.\d+)*)\s+', stage_name)
        if match:
            try:
                return [int(x) for x in match.group(1).split('.')]
            except ValueError:
                return None
        return None

    @classmethod
    def sort_siblings_key(cls, stage: Stage, prefix: Optional[str]):
        """Returns a sorting key for siblings. Ordered numerically by outline sequence first, fallback to creation time."""
        outline = cls.parse_outline_number(stage.stage_name, prefix)
        if outline is not None:
            return (0, outline, stage.created_at or datetime.min, stage.stage_id)
        else:
            return (1, [], stage.created_at or datetime.min, stage.stage_id)

    async def _populate_filenames(self, stages: List[StageResponse]) -> List[StageResponse]:
        """Fetch files from storage recursively and populate the filenames field for each stage response."""
        from src.app.storage import storage_service
        try:
            all_files = storage_service.list_files(prefix="", recursive=True)
            stage_files = {}
            for file_path in all_files:
                if "/" in file_path:
                    parts = file_path.split("/", 2)
                    if len(parts) > 2:
                        sid = parts[0]
                        fname = parts[2]
                        if fname:
                            stage_files.setdefault(sid, []).append(fname)
                    elif len(parts) == 2:
                        sid = parts[0]
                        fname = parts[1]
                        if fname:
                            stage_files.setdefault(sid, []).append(fname)
            for stage in stages:
                stage.filenames = stage_files.get(stage.stage_id, [])
        except Exception as e:
            logger.error(f"Error populating filenames: {e}")
            for stage in stages:
                stage.filenames = []
        return stages

    async def seed_system_stage(self) -> None:
        """Seed the unique root 'System' stage if it doesn't exist."""
        system_stage = await self.db.get(Stage, "stage_system")
        if not system_stage:
            result = await self.db.execute(
                select(Stage).where(Stage.stage_name == "System", Stage.parent_stage_id == None)
            )
            existing = result.scalar_one_or_none()
            if not existing:
                self.db.add(Stage(
                    stage_id="stage_system",
                    stage_name="System",
                    parent_stage_id=None,
                    stage_path="/System",
                    depth_level=0,
                    lineage_path=[],
                    is_root=True,
                    is_leaf=True,
                    visibility_scope="public",
                    created_by="system",
                ))
                await self.db.commit()
                logger.info("Seeded unique 'System' root stage.")

    async def _recompute_node_stats(self, node_id: Optional[str]) -> None:
        """
        Universally recalculate children_count, is_leaf, and is_root 
        based strictly on the database truth to prevent any drift.
        """
        if not node_id:
            return

        node = await self.db.get(Stage, node_id)
        if not node:
            return

        # Explicitly count direct children in the database
        result = await self.db.execute(
            select(func.count(Stage.stage_id)).where(
                Stage.parent_stage_id == node_id
            )
        )
        count = result.scalar() or 0

        node.children_count = count
        node.is_leaf = (count == 0)
        # System (depth 0) is the unique root node
        node.is_root = (node_id == "stage_system")

    async def reindex_wbs_codes(self) -> List[Dict[str, Any]]:
        """
        Reindexes WBS outline codes of the entire stage tree recursively.
        - "System" (depth 0) is the unique root stage. No prefix, no WBS numbering.
        - Depth 1 stages (direct children of "System") start the WBS prefixing/numbering:
          Each depth 1 stage gets a 3-character prefix (random if none). Named: prefix + index (e.g. arg1 Building).
        - Depth > 1 stages append '.x' to parent's outline code, inheriting prefix from their depth 1 ancestor.
        """
        # 1. Fetch all stages
        result = await self.db.execute(select(Stage))
        stages = result.scalars().all()
        
        # 2. Build parent-child map
        parent_map: Dict[Optional[str], List[Stage]] = {}
        for s in stages:
            parent_map.setdefault(s.parent_stage_id, []).append(s)
            
        changes = []
        
        # 3. Recursive helper to reindex
        async def traverse(parent_id: Optional[str], parent_outline: List[int], parent_path: str, depth: int, active_prefix: str):
            siblings = parent_map.get(parent_id, [])
            siblings.sort(key=lambda s: self.sort_siblings_key(s, s.wbs_prefix or active_prefix))
            
            for idx, stage in enumerate(siblings, start=1):
                if stage.stage_id == "stage_system" or (depth == 0 and stage.stage_name == "System"):
                    # System stage at depth 0
                    current_outline = []
                    new_name = "System"
                    current_prefix = ""
                    stage.wbs_prefix = None
                elif depth == 1:
                    # Depth 1 stages: direct children of "System"
                    # wbs_prefix may be None when the prefix was intentionally removed;
                    # in that case use just the outline number (no auto-reassignment).
                    wbs_prefix = stage.wbs_prefix

                    current_outline = [idx]
                    outline_str = str(idx)
                    wbs_code = f"{wbs_prefix}{outline_str}" if wbs_prefix else outline_str

                    base_name = self.extract_base_name(stage.stage_name, wbs_prefix or "")
                    new_name = f"{wbs_code} {base_name}"
                    current_prefix = wbs_prefix or ""
                else:
                    # Depth > 1 stages: inherit prefix from parent
                    stage.wbs_prefix = None  # stored only on depth 1 stages
                    current_outline = parent_outline + [idx]
                    outline_str = ".".join(str(x) for x in current_outline)
                    wbs_code = f"{active_prefix}{outline_str}"
                    
                    base_name = self.extract_base_name(stage.stage_name, active_prefix)
                    new_name = f"{wbs_code} {base_name}"
                    current_prefix = active_prefix
                    
                # Formulate new path
                new_path = f"{parent_path}/{new_name}".replace("//", "/")
                
                # Check if name, path, depth, or is_root has changed
                name_changed = (stage.stage_name != new_name)
                path_changed = (stage.stage_path != new_path)
                depth_changed = (stage.depth_level != depth)
                root_changed = (stage.is_root != (depth == 0))
                
                if name_changed or path_changed or depth_changed or root_changed:
                    old_name = stage.stage_name
                    old_path = stage.stage_path
                    
                    # Update attributes
                    stage.stage_name = new_name
                    stage.stage_path = new_path
                    stage.depth_level = depth
                    stage.is_root = (depth == 0)
                    
                    changes.append({
                        "stage_id": stage.stage_id,
                        "old_name": old_name,
                        "new_name": new_name,
                        "old_path": old_path,
                        "new_path": new_path,
                    })
                    
                # Traverse descendants
                await traverse(stage.stage_id, current_outline, new_path, depth + 1, current_prefix)
                
        # Start traversal from root (None)
        await traverse(None, [], "", 0, "")
        
        if changes:
            await self.db.flush()
            
        return changes

    async def create_stage(
        self, stage_data: StageCreate, created_by: Optional[str] = None
    ) -> StageResponse:
        """Create a new stage with hierarchical metadata."""
        # Enforce that all user-created stages must have a parent. If omitted, default to 'stage_system'
        parent_id = stage_data.parent_stage_id
        if not parent_id:
            parent_id = "stage_system"

        # Fetch parent stage
        result = await self.db.execute(
            select(Stage).where(Stage.stage_id == parent_id)
        )
        parent_stage = result.scalar_one_or_none()

        if not parent_stage:
            # If system root stage not seeded, seed it and try again
            if parent_id == "stage_system":
                await self.seed_system_stage()
                result = await self.db.execute(
                    select(Stage).where(Stage.stage_id == "stage_system")
                )
                parent_stage = result.scalar_one_or_none()
            
            if not parent_stage:
                raise ValueError(f"Parent stage {parent_id} not found")

        # Determine lineage path and depth level
        lineage_path = parent_stage.lineage_path + [parent_stage.stage_id]
        depth_level = parent_stage.depth_level + 1

        # Use temporary unique path to bypass SQL constraints before WBS reindexing
        temp_path = f"/temp_{uuid.uuid4().hex}"

        # Clean the input stage name
        clean_name = self.extract_base_name(stage_data.stage_name, stage_data.wbs_prefix)

        # Create new stage
        new_stage = Stage(
            stage_id=self.generate_stage_id(),
            stage_name=clean_name,
            parent_stage_id=parent_stage.stage_id,
            stage_path=temp_path,
            depth_level=depth_level,
            lineage_path=lineage_path,
            visibility_scope=stage_data.visibility_scope,
            is_root=False,  # only System is root
            is_leaf=True,   # Starts as leaf node
            wbs_prefix=stage_data.wbs_prefix,
            created_by=created_by,
        )

        self.db.add(new_stage)
        # Flush so the new stage is in the session and readable by reindexing
        await self.db.flush()

        # Run reindexing! This assigns outline numbers, formats names, and builds paths
        await self.reindex_wbs_codes()

        # Update parent's stats based on DB children count
        await self._recompute_node_stats(parent_stage.stage_id)

        await self.db.commit()
        await self.db.refresh(new_stage)

        # Automatically grant all permissions to the 'superadmin' role
        await self._grant_superadmin_stage_permission(new_stage.stage_id)

        # Invalidate caches
        await cache.invalidate_master_metadata()
        await cache.invalidate_stage_cache(new_stage.stage_id)

        return StageResponse.model_validate(new_stage)

    async def _grant_superadmin_stage_permission(self, stage_id: str) -> None:
        """Grant full permissions for the 'superadmin' role on a given stage (idempotent)."""
        ROLE = "superadmin"
        existing = await self.db.execute(
            select(StagePermission).where(
                StagePermission.stage_id == stage_id,
                StagePermission.role_name == ROLE,
            )
        )
        perm = existing.scalar_one_or_none()
        if perm:
            perm.can_view = True
            perm.can_create = True
            perm.can_edit = True
            perm.can_delete = True
            perm.can_manage_permissions = True
        else:
            self.db.add(StagePermission(
                stage_id=stage_id,
                role_name=ROLE,
                can_view=True,
                can_create=True,
                can_edit=True,
                can_delete=True,
                can_manage_permissions=True,
                granted_by="system",
            ))
        await self.db.commit()
        logger.info(f"Auto-granted '{ROLE}' full permissions on stage {stage_id}")

    async def get_stage(self, stage_id: str) -> Optional[StageResponse]:
        """Get stage by ID."""
        result = await self.db.execute(select(Stage).where(Stage.stage_id == stage_id))
        stage = result.scalar_one_or_none()

        if not stage:
            return None

        from src.app.storage import storage_service
        try:
            all_files = storage_service.list_files(prefix=f"{stage_id}/", recursive=True)
            filenames = []
            for file_path in all_files:
                if "/" in file_path:
                    parts = file_path.split("/", 2)
                    if len(parts) > 2:
                        fname = parts[2]
                    else:
                        fname = parts[1]
                    if fname:
                        filenames.append(fname)
                else:
                    filenames.append(file_path)
        except Exception as e:
            logger.error(f"Error fetching files for stage {stage_id}: {e}")
            filenames = []

        response = StageResponse.model_validate(stage)
        response.filenames = filenames
        return response

    async def update_stage(
        self, stage_id: str, stage_data: StageUpdate
    ) -> StageResponse:
        """Update stage name, prefix, and/or visibility."""
        if stage_id == "stage_system":
            raise ValueError("The unique 'System' root stage cannot be updated.")

        result = await self.db.execute(
            select(Stage).where(Stage.stage_id == stage_id)
        )
        stage = result.scalar_one_or_none()
        if not stage:
            raise ValueError(f"Stage {stage_id} not found")

        # Determine active prefix for name cleaning
        active_prefix = stage.wbs_prefix
        if not active_prefix and stage.depth_level > 1:
            ancestor_id = stage.lineage_path[1] if len(stage.lineage_path) > 1 else None
            if ancestor_id:
                ancestor = await self.db.get(Stage, ancestor_id)
                if ancestor:
                    active_prefix = ancestor.wbs_prefix

        # Clean and update stage name & WBS prefix & WBS number
        if stage.depth_level == 1:
            new_base = self.extract_base_name(stage_data.stage_name or stage.stage_name, active_prefix)
            
            new_prefix = stage.wbs_prefix
            if stage_data.wbs_prefix is not None:
                new_prefix = stage_data.wbs_prefix if stage_data.wbs_prefix else None
                
            outline = self.parse_outline_number(stage.stage_name, stage.wbs_prefix)
            current_num = outline[0] if (outline and len(outline) > 0) else 1
            new_num = stage_data.wbs_number if stage_data.wbs_number is not None else current_num
            
            # If removing prefix, check for duplicates with no-prefix name
            if stage_data.wbs_prefix is not None and not stage_data.wbs_prefix:
                wbs_code = f"{new_num}"
                no_prefix_name = f"{wbs_code} {new_base}"
                dup_result = await self.db.execute(
                    select(Stage).where(
                        Stage.stage_name == no_prefix_name,
                        Stage.stage_id != stage_id,
                    )
                )
                if dup_result.scalar_one_or_none():
                    raise ValueError(
                        f"Cannot remove prefix: a stage with name '{no_prefix_name}' "
                        f"already exists in the database."
                    )
                    
            wbs_code = f"{new_prefix}{new_num}" if new_prefix else f"{new_num}"
            stage.stage_name = f"{wbs_code} {new_base}"
            stage.wbs_prefix = new_prefix
            stage.stage_path = f"/temp_{uuid.uuid4().hex}"
        else:
            if stage_data.wbs_prefix is not None:
                raise ValueError("WBS prefix can only be configured on direct children of System (depth 1).")
            if stage_data.wbs_number is not None:
                raise ValueError("WBS number can only be configured on direct children of System (depth 1).")
            
            if stage_data.stage_name and stage_data.stage_name != stage.stage_name:
                clean_name = self.extract_base_name(stage_data.stage_name, active_prefix)
                stage.stage_name = clean_name
                stage.stage_path = f"/temp_{uuid.uuid4().hex}"

        if stage_data.visibility_scope:
            stage.visibility_scope = stage_data.visibility_scope

        await self.db.flush()

        # Run WBS re-indexing!
        await self.reindex_wbs_codes()

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
        responses = [StageResponse.model_validate(s) for s in stages]
        return await self._populate_filenames(responses)

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
        responses = [StageResponse.model_validate(s) for s in stages]
        return await self._populate_filenames(responses)

    async def get_stage_tree(
        self, 
        root_stage_id: Optional[str] = None, 
        max_depth: Optional[int] = None,
        user_id: Optional[str] = None
    ) -> List[StageTreeNode]:
        """Get hierarchical stage tree."""

        visible_stage_ids = None
        if user_id:
            from src.app.models.user import User
            from src.app.services.permission_service import PermissionService

            user = (await self.db.execute(select(User).where(User.user_id == user_id))).scalar_one_or_none()
            if not user:
                raise ValueError(f"User {user_id} not found")
            
            perm_service = PermissionService(self.db)
            user_perms = await perm_service.get_user_permissions(user.user_id)
            
            visible_stage_ids = set()
            for sid, perms in user_perms["stages"].items():
                if any(v for k, v in perms.items() if v):
                    visible_stage_ids.add(sid)
            
            visible_form_type_ids = set()
            for ftid, perms in user_perms["form_types"].items():
                if any(v for k, v in perms.items() if v):
                    visible_form_type_ids.add(ftid)
            
            if visible_form_type_ids:
                from src.app.models.stage_form_type import StageFormType
                mapping_res = await self.db.execute(
                    select(StageFormType.stage_id)
                    .where(StageFormType.form_type_id.in_(visible_form_type_ids))
                )
                for row in mapping_res.all():
                    visible_stage_ids.add(row[0])

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

        # Fetch all files from storage recursively
        from src.app.storage import storage_service
        stage_files = {}
        try:
            all_files = storage_service.list_files(prefix="", recursive=True)
            for file_path in all_files:
                if "/" in file_path:
                    parts = file_path.split("/", 2)
                    if len(parts) > 2:
                        sid = parts[0]
                        fname = parts[2]
                        if fname:
                            stage_files.setdefault(sid, []).append(fname)
                    elif len(parts) == 2:
                        sid = parts[0]
                        fname = parts[1]
                        if fname:
                            stage_files.setdefault(sid, []).append(fname)
        except Exception as e:
            logger.error(f"Error fetching files for stage tree: {e}")

        # Build tree structure
        stage_map: Dict[str, StageTreeNode] = {}
        root_nodes: List[StageTreeNode] = []

        if visible_stage_ids is not None:
            # Ensure ancestors are included so tree connectivity isn't broken
            ancestors = set()
            for stage in stages:
                if stage.stage_id in visible_stage_ids and stage.lineage_path:
                    ancestors.update(stage.lineage_path)
            visible_stage_ids.update(ancestors)

        for stage in stages:
            if visible_stage_ids is not None and stage.stage_id not in visible_stage_ids:
                continue

            from src.app.models.stage_form_type import StageFormType
            # Get form types for this stage
            form_types_result = await self.db.execute(
                select(FormType)
                .join(StageFormType, StageFormType.form_type_id == FormType.form_type_id)
                .where(StageFormType.stage_id == stage.stage_id)
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
                wbs_prefix=stage.wbs_prefix,
                created_by=stage.created_by,
                created_at=stage.created_at,
                updated_at=stage.updated_at,
                metadata_reference=stage.metadata_reference,
                filenames=stage_files.get(stage.stage_id, []),
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
            if root_stage_id not in stage_map:
                return []
            return [stage_map[root_stage_id]]

        return root_nodes

    async def get_descendant_stages(
        self, ancestor_stage_id: str, max_depth: Optional[int] = None
    ) -> List[StageResponse]:
        """Get all descendant stages using lineage."""
        query = select(Stage).where(
            text(":ancestor_id = ANY(lineage_path)").bindparams(ancestor_id=ancestor_stage_id)
        )

        if max_depth is not None:
            query = query.where(Stage.depth_level <= max_depth)

        result = await self.db.execute(
            query.order_by(Stage.depth_level, Stage.stage_name)
        )
        stages = result.scalars().all()

        responses = [StageResponse.model_validate(stage) for stage in stages]
        return await self._populate_filenames(responses)

    async def move_stage(
        self, stage_id: str, target_parent_id: Optional[str] = None, user_id: Optional[str] = None
    ) -> StageMoveResponse:
        
        start_time = time.time()
        
        if stage_id == "stage_system":
            raise ValueError("The unique 'System' root stage cannot be moved.")
            
        # --- fetch nodes ---
        stage = await self.db.get(Stage, stage_id)
        if not stage:
            raise ValueError(f"Stage {stage_id} not found")
            
        # Default target parent to System stage if omitted
        if not target_parent_id:
            target_parent_id = "stage_system"
            
        if target_parent_id == "stage_system":
            result = await self.db.execute(
                select(Stage).where(Stage.stage_id == "stage_system")
            )
            target_parent = result.scalar_one_or_none()
        else:
            target_parent = await self.db.get(Stage, target_parent_id)
            
        if not target_parent:
            raise ValueError(f"Target parent {target_parent_id} not found")
            
        if stage_id == target_parent_id:
            raise ValueError("Cannot move stage to itself")
            
        # --- prevent circular move ---
        if stage_id in target_parent.lineage_path:
            raise ValueError("Cannot move a node into its own descendant")
            
        old_parent_id = stage.parent_stage_id
        
        # --- fetch descendants ---
        descendants_result = await self.db.execute(
            select(Stage).where(
                text(":id = ANY(lineage_path)").bindparams(id=stage_id)
            )
        )
        descendants = descendants_result.scalars().all()
        
        # Save old paths and names for final renaming summary reporting
        old_nodes_info = {
            s.stage_id: {"name": s.stage_name, "path": s.stage_path}
            for s in [stage] + list(descendants)
        }
        
        old_path = stage.stage_path
        
        # --- update stage parenting details ---
        stage.parent_stage_id = target_parent.stage_id
        stage.lineage_path = target_parent.lineage_path + [target_parent.stage_id]
        stage.depth_level = len(stage.lineage_path)
        
        # Assign a temp path to avoid duplicate key issues during migration
        stage.stage_path = f"/temp_{uuid.uuid4().hex}"
        
        # --- update descendants parenting details ---
        for d in descendants:
            idx = d.lineage_path.index(stage_id)
            d.lineage_path = stage.lineage_path + [stage_id] + d.lineage_path[idx + 1 :]
            d.depth_level = len(d.lineage_path)
            d.stage_path = f"/temp_{uuid.uuid4().hex}"
            
        await self.db.flush()
        
        # --- run WBS re-indexing! ---
        # This will calculate new outline numbers, assign correct target WBS prefixes, 
        # rename stages, and set final paths!
        await self.reindex_wbs_codes()
        
        # --- recompute children counts + flags using centralized helper ---
        if old_parent_id:
            await self._recompute_node_stats(old_parent_id)
        await self._recompute_node_stats(target_parent.stage_id)
        await self._recompute_node_stats(stage_id)
        
        await self.db.commit()
        
        # Re-fetch stage from db to get final correct values
        await self.db.refresh(stage)
        
        # --- populate moved_stages list for response ---
        moved_stages = []
        for sid, old_info in old_nodes_info.items():
            updated = await self.db.get(Stage, sid)
            if updated:
                moved_stages.append(StageMovedNode(
                    stage_id=sid,
                    old_name=old_info["name"],
                    new_name=updated.stage_name,
                    old_path=old_info["path"],
                    new_path=updated.stage_path
                ))
                
        # --- cache ---
        await cache.invalidate_master_metadata()
        await cache.invalidate_stage_cache(stage_id)
        await cache.invalidate_stage_cache(target_parent.stage_id)
        if old_parent_id:
            await cache.invalidate_stage_cache(old_parent_id)
            
        duration_ms = (time.time() - start_time) * 1000
        
        return StageMoveResponse(
            stage_id=stage_id,
            old_path=old_path,
            new_path=stage.stage_path,
            affected_stages_count=len(descendants) + 1,
            operation_duration_ms=duration_ms,
            moved_stages=moved_stages
        )

    async def delete_stage(
        self, stage_id: str, recursive: bool = True, preview: bool = False
    ) -> Dict[str, Any]:
        """Delete stage and all descendants recursively.

        Args:
            stage_id: The ID of the stage to delete
            recursive: If True, delete all descendants. If False, delete only the stage.
            preview: If True, return what would be deleted without actually deleting.

        Returns:
            Dictionary with delete results or preview data.
        """
        if stage_id == "stage_system":
            raise ValueError("The unique 'System' root stage cannot be deleted.")

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
            # IMPORTANT: Put descendants first to prevent foreign key cascade errors
            stage_ids = [d.stage_id for d in descendants] + [stage_id]
        else:
            stage_ids = [stage_id]
            descendants = []

        if preview:
            # Return preview of what would be deleted
            return {
                "preview": True,
                "stage_to_delete": {
                    "stage_id": stage.stage_id,
                    "stage_name": stage.stage_name,
                    "stage_path": stage.stage_path,
                    "depth_level": stage.depth_level,
                },
                "descendants": [
                    {
                        "stage_id": d.stage_id,
                        "stage_name": d.stage_name,
                        "stage_path": d.stage_path,
                        "depth_level": d.depth_level,
                    }
                    for d in descendants
                ],
                "total_stages": len(stage_ids),
                "total_items": len(stage_ids),
            }

        # Delete stages (cascade will handle form types and permissions)
        for sid in stage_ids:
            result = await self.db.execute(
                select(Stage).where(Stage.stage_id == sid)
            )
            s = result.scalar_one_or_none()
            if s:
                await self.db.delete(s)

        # Explicitly flush pending deletes to the database transaction
        await self.db.flush()

        # Compact WBS outline numbers by running re-indexing!
        await self.reindex_wbs_codes()

        # Update parent's state if stage had a parent based on DB count
        if parent_id:
            await self._recompute_node_stats(parent_id)
            logger.info(f"Updated parent {parent_id} stats after deletion.")

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