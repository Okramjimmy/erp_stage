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
                parsed_data = json.loads(record.data)
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

    async def create(self, payload: FormRecordCreate) -> FormRecordResponse:
        ft = await self.db.get(FormType, payload.form_type_id)
        if not ft:
            raise ValueError(f"FormType {payload.form_type_id} not found")

        docname = await self._next_docname(payload.form_type_id, ft.form_name)

        record = FormRecord(
            record_id=self._new_id(),
            form_type_id=payload.form_type_id,
            docname=docname,
            status="Draft",
            data=json.dumps(payload.data),
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
        record.data = json.dumps(payload.data)
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
