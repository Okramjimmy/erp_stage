"""Service for managing workflow assignments (Stage + FormType + Role → User)."""

import logging
from typing import List, Optional
from uuid import UUID

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.workflow_assignment import WorkflowAssignment
from src.app.models.stage import Stage
from src.app.schemas.workflow_assignment import (
    WorkflowAssignmentCreate,
    WorkflowAssignmentResponse,
    WorkflowAssignmentUpdate,
)

logger = logging.getLogger(__name__)


class WorkflowAssignmentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_assignment(
        self,
        payload: WorkflowAssignmentCreate,
        assigned_by: Optional[str] = None,
    ) -> WorkflowAssignmentResponse:
        """Create a new workflow assignment. Raises if a duplicate active assignment exists."""
        # Check for existing active assignment with the same key
        existing = await self.db.execute(
            select(WorkflowAssignment).where(
                and_(
                    WorkflowAssignment.stage_id == payload.stage_id,
                    WorkflowAssignment.form_type_id == payload.form_type_id,
                    WorkflowAssignment.role == payload.role,
                    WorkflowAssignment.active == True,
                )
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError(
                f"Active assignment already exists for "
                f"stage={payload.stage_id}, form_type={payload.form_type_id}, role={payload.role}. "
                f"Delete or update it first."
            )

        assignment = WorkflowAssignment(
            stage_id=payload.stage_id,
            form_type_id=payload.form_type_id,
            role=payload.role,
            user_id=payload.user_id,
            assigned_by=assigned_by,
        )
        self.db.add(assignment)
        await self.db.commit()
        await self.db.refresh(assignment)
        logger.info(
            f"Created workflow assignment: {payload.stage_id}/{payload.form_type_id} "
            f"role={payload.role} → user={payload.user_id}"
        )
        return WorkflowAssignmentResponse.model_validate(assignment)

    async def get_assignments(
        self,
        stage_id: str,
        form_type_id: str,
    ) -> List[WorkflowAssignmentResponse]:
        """List all active assignments for a stage + form_type combination."""
        result = await self.db.execute(
            select(WorkflowAssignment).where(
                and_(
                    WorkflowAssignment.stage_id == stage_id,
                    WorkflowAssignment.form_type_id == form_type_id,
                    WorkflowAssignment.active == True,
                )
            )
        )
        rows = result.scalars().all()
        return [WorkflowAssignmentResponse.model_validate(r) for r in rows]

    async def get_assigned_user(
        self,
        stage_id: str,
        form_type_id: str,
        role: str,
    ) -> Optional[str]:
        """Resolve the user_id assigned to a specific role for a stage+form_type.

        Checks the target stage first, then recursively walks up the parent stages
        to inherit workflow assignments if not overridden.
        """
        current_stage_id = stage_id
        visited = set()
        
        while current_stage_id and current_stage_id not in visited:
            visited.add(current_stage_id)
            
            result = await self.db.execute(
                select(WorkflowAssignment.user_id).where(
                    and_(
                        WorkflowAssignment.stage_id == current_stage_id,
                        WorkflowAssignment.form_type_id == form_type_id,
                        WorkflowAssignment.role == role,
                        WorkflowAssignment.active == True,
                    )
                )
            )
            user_id = result.scalar_one_or_none()
            if user_id:
                logger.info(f"Resolved role={role} to user={user_id} on stage={current_stage_id} (requested={stage_id})")
                return user_id
                
            if current_stage_id == "stage_system":
                break
                
            stage_result = await self.db.execute(
                select(Stage.parent_stage_id).where(Stage.stage_id == current_stage_id)
            )
            parent_id = stage_result.scalar_one_or_none()
            if not parent_id:
                if current_stage_id != "stage_system":
                    current_stage_id = "stage_system"
                else:
                    break
            else:
                current_stage_id = parent_id
                
        logger.warning(f"Could not resolve role={role} on stage={stage_id} or any ancestors")
        return None

    async def update_assignment(
        self,
        assignment_id: UUID,
        payload: WorkflowAssignmentUpdate,
    ) -> WorkflowAssignmentResponse:
        """Change the user assigned to an existing assignment."""
        assignment = await self.db.get(WorkflowAssignment, assignment_id)
        if not assignment:
            raise ValueError(f"Assignment {assignment_id} not found")

        assignment.user_id = payload.user_id
        await self.db.commit()
        await self.db.refresh(assignment)
        logger.info(f"Updated assignment {assignment_id} → user={payload.user_id}")
        return WorkflowAssignmentResponse.model_validate(assignment)

    async def delete_assignment(self, assignment_id: UUID) -> None:
        """Hard-delete an assignment."""
        assignment = await self.db.get(WorkflowAssignment, assignment_id)
        if not assignment:
            raise ValueError(f"Assignment {assignment_id} not found")

        await self.db.delete(assignment)
        await self.db.commit()
        logger.info(f"Deleted assignment {assignment_id}")
