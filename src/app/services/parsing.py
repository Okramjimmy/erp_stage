"""Parsing service for managing dynamic form parsing."""

import json
import logging
import uuid
from typing import List, Optional
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from aiohttp import ClientSession, ClientTimeout, FormData

logger = logging.getLogger(__name__)


class ParsingService:
    """Service for Parsing operations."""

    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def parse_form(self, file_path: str) -> dict:
        """Parse a file and return json."""
        import asyncio
        import re

        def slugify(text: str) -> str:
            text = text.lower()
            text = re.sub(r'[^a-z0-9]+', '_', text)
            text = re.sub(r'_+', '_', text)
            return text.strip('_')

        base_url = "http://13.214.237.209:8001/api/v1"

        with open(file_path, "rb") as f:
            form_data = FormData()
            form_data.add_field("file", f)

            async with ClientSession(timeout=ClientTimeout(total=300)) as session:
                async with session.post(f"{base_url}/extract-semantic", data=form_data) as resp:
                    data = await resp.json()
                    
                    job_id = data.get("job_id")
                    if not job_id:
                        raise ValueError("No job_id returned from extract-semantic")
                    
                    result = None
                    max_attempts = 40  # 40 * 3 = 120 seconds (2 minutes)
                    
                    for attempt in range(max_attempts):
                        await asyncio.sleep(3)
                        
                        async with session.get(f"{base_url}/jobs/{job_id}") as res:
                            job_data = await res.json()
                        
                        status = job_data.get("status")
                        logger.info(f"Polling job {job_id}, attempt {attempt+1}/{max_attempts}, status: {status}")
                        
                        if status == "completed":
                            async with session.get(f"{base_url}/jobs/{job_id}/result?format=json") as res_res:
                                result = await res_res.json()
                            break
                        elif status == "failed":
                            raise ValueError(f"Job failed with status {status}")
                    else:
                        raise TimeoutError("Parsing job timed out after 2 minutes")
                    
                    if not result:
                        raise ValueError("No result obtained from parsing job")

                    # Group questions by section
                    sections_map = {}
                    section_order = []
                    checklist = result.get("checklist", {})
                    questions = checklist.get("questions", [])
                    
                    for q in questions:
                        q_section = q.get("section")
                        if not q_section:
                            sec_path = q.get("section_path")
                            if sec_path and isinstance(sec_path, list) and len(sec_path) > 0:
                                q_section = sec_path[-1]
                            else:
                                q_section = "General"
                                
                        if q_section not in sections_map:
                            sections_map[q_section] = []
                            section_order.append(q_section)
                        sections_map[q_section].append(q)

                    fields = []
                    
                    def generate_fieldname(base_slug):
                        ft_slug = slugify(base_slug)
                        existing_fns = {f["fieldname"] for f in fields}
                        counter = 1
                        fn = f"{ft_slug}_{counter}"
                        while fn in existing_fns:
                            counter += 1
                            fn = f"{ft_slug}_{counter}"
                        return fn

                    for sec_name in section_order:
                        # Append Section Break
                        fn_sec = generate_fieldname("Section Break")
                        fields.append({
                            "label": sec_name,
                            "fieldtype": "Section Break",
                            "fieldname": fn_sec,
                            "collapsible": False
                        })
                        
                        # Append all questions of this section
                        q_idx = 1
                        for q in sections_map[sec_name]:
                            lbl = q.get("question", "")
                            response_type = q.get("response_type", "")
                            
                            def append_field(ftype, label, options="", depends_on="", description=""):
                                fn = generate_fieldname(ftype)
                                field_data = {
                                    "label": label,
                                    "fieldname": fn,
                                    "fieldtype": ftype,
                                    "options": options,
                                    "required": False,
                                    "unique": False,
                                    "read_only": False,
                                    "hidden": False,
                                    "bold": False,
                                    "in_list_view": False,
                                    "in_filter": False,
                                    "search_index": False,
                                    "print_hide": False,
                                    "no_copy": False,
                                    "allow_on_submit": False,
                                    "description": description if description is not None else "",
                                    "default": "",
                                    "placeholder": "",
                                    "field_number": q_idx,
                                    "filed_number": q_idx
                                }
                                if depends_on:
                                    field_data["depends_on"] = depends_on
                                fields.append(field_data)
                                return fn

                            if response_type in ("yes_or_no", "yes_no_na", "yes_no"):
                                options = "Yes\nNo\nNA" if "na" in response_type else "Yes\nNo"
                                select_fn = append_field("Select", lbl, options=options, description=q.get("question_code", ""))
                                append_field("Long Text", "Remarks", depends_on=f"eval:doc.{select_fn} == 'Yes'")
                                append_field("Attach", "Attachment", depends_on=f"eval:doc.{select_fn} == 'Yes'")
                            else:
                                field_type = "Long Text"
                                if response_type:
                                    rt_lower = response_type.lower()
                                    if rt_lower == "date":
                                        field_type = "Date"
                                    elif rt_lower in ("number", "integer"):
                                        field_type = "Int"
                                    elif rt_lower == "text":
                                        field_type = "Data"
                                append_field(field_type, lbl, description=q.get("question_code", ""))
                            
                            q_idx += 1
                        
                    return {
                        "job_id": job_id,
                        "status": "completed",
                        "document_name": checklist.get("documengenerate_fieldnamet_name"),
                        "form_metadata": {
                            "fields": fields
                        }
                    }
