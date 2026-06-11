import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.form_record import FormRecord
from src.app.models.form_type import FormType
from src.app.models.form_action import FormAction
from src.app.schemas.form_record import (
    FormRecordCreate,
    FormRecordResponse,
    FormRecordUpdate,
)
from src.app.storage.minio_storage import storage_service
from src.app.services.workflow_assignment_service import WorkflowAssignmentService
from transitions import Machine

class RecordContext:
    def __init__(self, state):
        self.state = state


logger = logging.getLogger(__name__)


class FormRecordService:
    def __init__(self, db: AsyncSession):
        self.db = db

    @staticmethod
    def _new_id() -> str:
        return f"rec_{uuid.uuid4().hex[:12]}"



    @staticmethod
    def _abbrev(form_name: str) -> str:
        words = form_name.upper().split()
        if len(words) == 1:
            return words[0][:6]
        return "".join(w[0] for w in words[:5])

    async def _next_docname(self, form_type_id: str, form_name: str) -> str:
        result = await self.db.execute(
            select(func.count()).where(FormRecord.form_type_id == form_type_id)
        )
        count = result.scalar() or 0
        return f"{self._abbrev(form_name)}-{count + 1:05d}"

    def _parse(self, record: FormRecord) -> FormRecordResponse:
        parsed_data = None
        if record.data:
            try:
                parsed_data = record.data
            except Exception:
                parsed_data = {}
        return FormRecordResponse.model_validate({
            "record_id": record.record_id,
            "form_type_id": record.form_type_id,
            "stage_id": record.stage_id,
            "docname": record.docname,
            "status": record.status,
            "assigned_role": record.assigned_role,
            "assigned_to": record.assigned_to,
            "assigned_at": record.assigned_at,
            "data": parsed_data,
            "schema_snapshot": record.schema_snapshot,
            "form_version": record.form_version,
            "amended_from": record.amended_from,
            "submitted_by": record.submitted_by,
            "submitted_at": record.submitted_at,
            "created_by": record.created_by,
            "created_at": record.created_at,
            "updated_at": record.updated_at,
        })

    def _get_attach_field(self, ft: FormType, field_name: str) -> Optional[dict]:
        """Look up a field definition by name; return it only if it is an Attach type."""
        if not ft.schema_reference:
            logger.error(f"FormType {ft.form_type_id} has no schema_reference")
            return None
        schema_reference = ft.schema_reference
        for field in schema_reference.get("fields", []):
            logger.info(f"Field {field}")
            if field.get("fieldname") == field_name:
                field_type = field.get("fieldtype") or ""
                if field_type in ("Attach", "Attach Image"):
                    logger.info(f"Attach field found: {field}")
                    return field
        return None

    def _build_minio_path(self, ft: FormType, field: dict, filename: str, record_id: str) -> str:
        """Build the canonical MinIO path: form_type_id/record_id/field_id/filename."""
        field_id = field.get("fieldname")
        return f"{ft.form_type_id}/{record_id}/{field_id}/{filename}"

    def _process_attachments(self, ft: FormType, data: dict, record_id: str) -> dict:
        """Ensure attachment fields contain the full path."""
        if not data or not ft.schema_reference:
            return data

        schema_ref = ft.schema_reference
        if not isinstance(schema_ref, dict):
            return data

        for field in schema_ref.get("fields", []):
            field_type = field.get("fieldtype") or ""
            if field_type not in ("Attach", "Attach Image"):
                continue
            field_name = field.get("fieldname")
            if not field_name or field_name not in data:
                continue
            value = data[field_name]
            if not value or not isinstance(value, str):
                continue

            # If the value is not a full path (i.e. does not have '/'), build the full path
            if '/' not in value:
                value = self._build_minio_path(ft, field, value, record_id)
            data[field_name] = value
                
        return data

    async def upload_attachment(
        self,
        record_id: str,
        field_name: str,
        file_bytes: bytes,
        filename: str,
        content_type: str = "application/octet-stream",
    ) -> FormRecordResponse:
        """Upload a file to MinIO and store the canonical path in record.data[field_name]."""
        record = await self.db.get(FormRecord, record_id)
        if not record:
            raise ValueError(f"Record {record_id} not found")
        if record.status != "Draft":
            raise ValueError("Attachments can only be uploaded for Draft records")

        ft = await self.db.get(FormType, record.form_type_id)
        if not ft:
            raise ValueError(f"FormType {record.form_type_id} not found")

        attach_field = self._get_attach_field(ft, field_name)
        if attach_field is None:
            raise ValueError(
                f"Field '{field_name}' is not an Attach field in form type '{ft.form_name}'"
            )

        object_name = self._build_minio_path(ft, attach_field, filename, record_id=record_id)

        success = storage_service.upload_file(
            file_data=file_bytes,
            object_name=object_name,
            content_type=content_type,
        )
        if not success:
            raise RuntimeError(f"Failed to upload file to MinIO at path: {object_name}")

        logger.info(f"Uploaded attachment for record {record_id}, field '{field_name}' -> {object_name}")

        # Persist the full path in the record
        data = dict(record.data) if record.data else {}
        data[field_name] = object_name
        record.data = data
        logger.debug(f"------Updated record data: {data}")
        await self.db.commit()
        await self.db.refresh(record)
        return self._parse(record)

    async def create(
        self,
        payload: FormRecordCreate,
        created_by: str = "system"
    ) -> FormRecordResponse:
        ft = await self.db.get(FormType, payload.form_type_id)
        if not ft:
            raise ValueError(f"FormType {payload.form_type_id} not found")

        docname = await self._next_docname(payload.form_type_id, ft.form_name)
        record_id = self._new_id()

        # Process attachments
        processed_data = self._process_attachments(ft, payload.data, record_id)

        record = FormRecord(
            record_id=record_id,
            form_type_id=payload.form_type_id,
            stage_id=payload.stage_id,
            docname=docname,
            status="Draft",
            assigned_role="worker",
            assigned_to=created_by,
            assigned_at=datetime.now(timezone.utc),
            data=processed_data,
            created_by=created_by,
            form_version=ft.version,
            schema_snapshot=ft.schema_reference,
        )
        self.db.add(record)
        await self.db.commit()
        await self.db.refresh(record)
        return self._parse(record)

    async def get(self, record_id: str) -> Optional[FormRecordResponse]:
        record = await self.db.get(FormRecord, record_id)
        return self._parse(record) if record else None

    async def list_by_form_type(
        self, form_type_id: str, skip: int = 0, limit: int = 50
    ) -> tuple[List[FormRecordResponse], int]:
        q = select(FormRecord).where(FormRecord.form_type_id == form_type_id)
        total_res = await self.db.execute(
            select(func.count()).select_from(q.subquery())
        )
        total = total_res.scalar() or 0
        res = await self.db.execute(
            q.order_by(FormRecord.created_at.desc()).offset(skip).limit(limit)
        )
        items = [self._parse(r) for r in res.scalars().all()]
        return items, total

    async def update(
        self, record_id: str, payload: FormRecordUpdate
    ) -> FormRecordResponse:
        record = await self.db.get(FormRecord, record_id)
        if not record:
            raise ValueError(f"Record {record_id} not found")
        if record.status != "Draft":
            raise ValueError("Only Draft records can be edited")

        ft = await self.db.get(FormType, record.form_type_id)
        processed_data = self._process_attachments(ft, payload.data, record_id)

        record.data = processed_data
        await self.db.commit()
        await self.db.refresh(record)
        return self._parse(record)

    def _build_machine(self, workflow_data: dict, current_state: str) -> tuple[Machine, RecordContext]:
        if not workflow_data:
            # Fallback default workflow
            workflow_data = {
                "states": ["Draft", "Submitted", "Verified", "Completed", "Cancelled"],
                "initial": "Draft",
                "transitions": [
                    {"trigger": "submit", "source": "Draft", "dest": "Submitted"},
                    {"trigger": "verify", "source": "Submitted", "dest": "Verified"},
                    {"trigger": "amend", "source": "Verified", "dest": "Completed"},
                    {"trigger": "cancel", "source": ["Submitted", "Verified"], "dest": "Draft"}
                ]
            }

        states = workflow_data.get("states", [])
        transitions = workflow_data.get("transitions", [])
        
        # Filter out custom keys (actor_role, next_role) to prevent TypeError in transitions library
        clean_transitions = []
        valid_keys = {"trigger", "source", "dest", "conditions", "unless", "before", "after", "prepare"}
        for t in transitions:
            clean_t = {k: v for k, v in t.items() if k in valid_keys}
            clean_transitions.append(clean_t)
        
        ctx = RecordContext(current_state)
        machine = Machine(model=ctx, states=states, transitions=clean_transitions, initial=current_state)
        return machine, ctx

    def _find_transition(self, workflow_data: dict, trigger: str, current_state: str) -> Optional[dict]:
        """Find the matching transition definition from workflow_data."""
        if not workflow_data:
            return None
        for t in workflow_data.get("transitions", []):
            sources = t.get("source", [])
            if isinstance(sources, str):
                sources = [sources]
            if t.get("trigger") == trigger and current_state in sources:
                return t
        return None

    async def _can_execute_trigger(self, record: FormRecord, trigger: str, user_data: dict, workflow_data: dict) -> bool:
        user_roles = user_data.get("roles", [])
        if "superadmin" in user_roles:
            return True
            
        # 1. Check actor_role constraint from the transition definition
        if workflow_data:
            transition = self._find_transition(workflow_data, trigger, record.status)
            if transition:
                actor_role = transition.get("actor_role")
                if actor_role and actor_role not in user_roles:
                    return False
            
        # 2. Ownership check: if the record is assigned to a specific user,
        #    only that user (or superadmin) can act on it
        if record.assigned_to:
            if user_data.get("user_id") != record.assigned_to:
                return False
            
        # 3. Must satisfy explicit RBAC form type permissions (if mapped)
        t = trigger.lower()
        perm_type = None
        if t in ("submit",):
            perm_type = "can_submit"
        elif t in ("verify", "approve"):
            perm_type = "can_verify"
        elif t in ("cancel", "reject"):
            perm_type = "can_cancel"
        elif t in ("amend",):
            perm_type = "can_amend"
            
        if perm_type:
            from src.app.services.permission_service import PermissionService
            perm_service = PermissionService(self.db)
            has_perm = await perm_service.check_form_type_permission(
                user_data.get("user_id"), 
                record.form_type_id, 
                perm_type
            )
            if not has_perm:
                return False
                
        return True

    async def get_available_actions(self, record_id: str, user_data: dict) -> list[str]:
        record = await self.db.get(FormRecord, record_id)
        if not record: return []

        ft = await self.db.get(FormType, record.form_type_id)
        if ft.workflow_data is None:
            raise ValueError(f"FormType {record.form_type_id} has no workflow")
        
        # Get all potential machine triggers
        machine, ctx = self._build_machine(ft.workflow_data, record.status)
        triggers = machine.get_triggers(ctx.state)
        
        valid_triggers = []
        for t in triggers:
            if not t.startswith('to_'):
                if await self._can_execute_trigger(record, t, user_data, ft.workflow_data):
                    valid_triggers.append(t)
                    
        return valid_triggers

    async def process_transition(self, record_id: str, trigger: str, user_data: dict, remarks: str | None = None) -> FormRecordResponse:
        record = await self.db.get(FormRecord, record_id)
        if not record:
            raise ValueError(f"Record {record_id} not found")
        
        ft = await self.db.get(FormType, record.form_type_id)
        if ft.workflow_data is None:
            raise ValueError(f"FormType {record.form_type_id} has no workflow")
            
        # Security check: Does user have RBAC and workflow assignment rights for this trigger?
        if not await self._can_execute_trigger(record, trigger, user_data, ft.workflow_data):
             raise ValueError("You do not have permission to execute this transition")
        
        old_state = record.status
             
        machine, ctx = self._build_machine(ft.workflow_data, old_state)
        
        valid_triggers = machine.get_triggers(ctx.state)
        if trigger not in valid_triggers:
             raise ValueError(f"Invalid transition '{trigger}' from state '{ctx.state}'")
             
        try:
             getattr(ctx, trigger)()
        except Exception as e:
             raise ValueError(f"Transition failed: {e}")
             
        new_state = ctx.state
        record.status = new_state
        
        # ── Assignment chain: resolve next owner from workflow_assignments ──
        transition_def = self._find_transition(ft.workflow_data, trigger, old_state)
        next_role = transition_def.get("next_role") if transition_def else None

        if next_role:
            # Look up the user assigned to next_role for this stage+form_type
            assignment_svc = WorkflowAssignmentService(self.db)
            next_user_id = await assignment_svc.get_assigned_user(
                stage_id=record.stage_id,
                form_type_id=record.form_type_id,
                role=next_role,
            )
            if not next_user_id:
                raise ValueError(
                    f"No workflow assignment found for role '{next_role}' "
                    f"in stage '{record.stage_id}', form type '{record.form_type_id}'. "
                    f"Please configure assignments before processing transitions."
                )
            record.assigned_role = next_role
            record.assigned_to = next_user_id
            record.assigned_at = datetime.now(timezone.utc)
        else:
            # Terminal state — clear assignment fields
            record.assigned_role = None
            record.assigned_to = None
            record.assigned_at = None
             
        if trigger == "submit" and not record.submitted_by:
             record.submitted_by = user_data.get("user_id")
             record.submitted_at = datetime.now(timezone.utc)
        
        action = FormAction(
            record_id=record.record_id,
            action_type=trigger,
            from_state=old_state,
            to_state=new_state,
            performed_by=user_data.get("user_id"),
            remarks=remarks,
        )

        self.db.add(action)
             
        await self.db.commit()
        await self.db.refresh(record)
        return self._parse(record)

    async def delete(self, record_id: str) -> None:
        record = await self.db.get(FormRecord, record_id)
        if not record:
            raise ValueError(f"Record {record_id} not found")
        if record.status != "Draft":
            raise ValueError("Only Draft records can be deleted")

        # FormType lookup
        form_type = await self.db.get(FormType, record.form_type_id)
        if not form_type:
            raise ValueError(f"FormType {record.form_type_id} not found where it should be")

        # Minio delete folder
        record_path = f"{form_type.form_type_id}/{record.record_id}"
        condition = storage_service.delete_file(record_path)
        if not condition:
            raise ValueError(f"Failed to delete record {record_id}")
            
        await self.db.delete(record)
        await self.db.commit()
