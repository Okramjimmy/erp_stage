import json
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.models.form_record import FormRecord
from src.app.models.form_type import FormType
from src.app.schemas.form_record import (
    FormRecordCreate,
    FormRecordResponse,
    FormRecordUpdate,
)
from src.app.storage.minio_storage import storage_service

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
            "docname": record.docname,
            "status": record.status,
            "data": parsed_data,
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
        schema_reference = json.loads(ft.schema_reference)
        for field in schema_reference.get("fields", []):
            logger.info(f"Field {field}")
            if field.get("fieldname") == field_name:
                field_type = field.get("fieldtype") or ""
                if field_type in ("Attach", "Attach Image"):
                    logger.info(f"Attach field found: {field}")
                    return field
        return None

    def _build_minio_path(self, ft: FormType, field: dict, filename: str) -> str:
        """Build the canonical MinIO path: stage_id/form_name/field_label/filename."""
        field_label = field.get("label") or field.get("fieldname")
        return f"{ft.stage_id}/{ft.form_name}/{field_label}/{filename}"

    def _process_attachments(self, ft: FormType, data: dict) -> dict:
        """Relocate any attachment paths that are not already in the canonical location."""
        if not data or not ft.schema_reference:
            return data

        schema = ft.schema_reference
        if not isinstance(schema, dict):
            return data

        for field in schema.get("fields", []):
            field_type = field.get("fieldtype") or ""
            if field_type not in ("Attach", "Attach Image"):
                continue
            field_name = field.get("fieldname")
            if not field_name or field_name not in data:
                continue
            value = data[field_name]
            if not value or not isinstance(value, str):
                continue

            filename = value.split('/')[-1]
            expected_path = self._build_minio_path(ft, field, filename)

            if value != expected_path:
                success = storage_service.move_file(value, expected_path)
                if success:
                    data[field_name] = expected_path
                    logger.info(f"Moved attachment {value} -> {expected_path}")
                else:
                    logger.warning(f"Failed to move attachment {value} -> {expected_path}")
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
        if record.status not in ("Draft", "Amended"):
            raise ValueError("Attachments can only be uploaded for Draft or Amended records")

        ft = await self.db.get(FormType, record.form_type_id)
        if not ft:
            raise ValueError(f"FormType {record.form_type_id} not found")

        attach_field = self._get_attach_field(ft, field_name)
        logger.info(f"`~~~~~~~~~~~~~~~~~~~~~~~~~Attach field for record {record_id}, field '{field_name}' -> {attach_field}")
        if attach_field is None:
            raise ValueError(
                f"Field '{field_name}' is not an Attach field in form type '{ft.form_name}'"
            )

        object_name = self._build_minio_path(ft, attach_field, filename)

        success = storage_service.upload_file(
            file_data=file_bytes,
            object_name=object_name,
            content_type=content_type,
        )
        if not success:
            raise RuntimeError(f"Failed to upload file to MinIO at path: {object_name}")

        logger.info(f"Uploaded attachment for record {record_id}, field '{field_name}' -> {object_name}")

        # Persist the path in the record
        data = dict(record.data) if record.data else {}
        data[field_name] = object_name
        record.data = data
        await self.db.commit()
        await self.db.refresh(record)
        return self._parse(record)

    async def create(self, payload: FormRecordCreate) -> FormRecordResponse:
        ft = await self.db.get(FormType, payload.form_type_id)
        if not ft:
            raise ValueError(f"FormType {payload.form_type_id} not found")

        docname = await self._next_docname(payload.form_type_id, ft.form_name)
        
        # Process attachments
        processed_data = self._process_attachments(ft, payload.data)

        record = FormRecord(
            record_id=self._new_id(),
            form_type_id=payload.form_type_id,
            docname=docname,
            status="Draft",
            data=processed_data,
            created_by=payload.created_by,
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
        if record.status not in ("Draft", "Amended"):
            raise ValueError("Only Draft or Amended records can be edited")
            
        ft = await self.db.get(FormType, record.form_type_id)
        processed_data = self._process_attachments(ft, payload.data)
        
        record.data = processed_data
        await self.db.commit()
        await self.db.refresh(record)
        return self._parse(record)

    async def submit(self, record_id: str, submitted_by: str = "system") -> FormRecordResponse:
        record = await self.db.get(FormRecord, record_id)
        if not record:
            raise ValueError(f"Record {record_id} not found")
        if record.status != "Draft":
            raise ValueError("Only Draft records can be submitted")
        record.status = "Submitted"
        record.submitted_by = submitted_by
        record.submitted_at = datetime.now(timezone.utc)
        await self.db.commit()
        await self.db.refresh(record)
        return self._parse(record)

    async def cancel(self, record_id: str) -> FormRecordResponse:
        record = await self.db.get(FormRecord, record_id)
        if not record:
            raise ValueError(f"Record {record_id} not found")
        if record.status != "Submitted":
            raise ValueError("Only Submitted records can be cancelled")
        record.status = "Cancelled"
        await self.db.commit()
        await self.db.refresh(record)
        return self._parse(record)

    async def amend(self, record_id: str, created_by: str = "system") -> FormRecordResponse:
        original = await self.db.get(FormRecord, record_id)
        if not original:
            raise ValueError(f"Record {record_id} not found")
        if original.status != "Submitted":
            raise ValueError("Only Submitted records can be amended")

        ft = await self.db.get(FormType, original.form_type_id)
        docname = await self._next_docname(original.form_type_id, ft.form_name)

        amended = FormRecord(
            record_id=self._new_id(),
            form_type_id=original.form_type_id,
            docname=docname,
            status="Draft",
            data=original.data,
            amended_from=original.record_id,
            created_by=created_by,
        )
        self.db.add(amended)
        original.status = "Amended"
        await self.db.commit()
        await self.db.refresh(amended)
        return self._parse(amended)

    async def delete(self, record_id: str) -> None:
        record = await self.db.get(FormRecord, record_id)
        if not record:
            raise ValueError(f"Record {record_id} not found")
        if record.status == "Submitted":
            raise ValueError("Submitted records cannot be deleted")
        await self.db.delete(record)
        await self.db.commit()
