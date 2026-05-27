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

                    # Map parsed result to form builder fields schema
                    fields = []
                    current_section = None
                    checklist = result.get("checklist", {})
                    questions = checklist.get("questions", [])
                    
                    for q in questions:
                        q_section = None
                        sec_path = q.get("section_path")
                        if sec_path and isinstance(sec_path, list) and len(sec_path) > 0:
                            q_section = sec_path[0]
                        elif q.get("section"):
                            q_section = q.get("section")
                            
                        if q_section and q_section != current_section:
                            ft_slug = slugify("Section Break")
                            existing_fns = {f["fieldname"] for f in fields}
                            counter = 1
                            fn = f"{ft_slug}_{counter}"
                            while fn in existing_fns:
                                counter += 1
                                fn = f"{ft_slug}_{counter}"
                                
                            fields.append({
                                "label": q_section,
                                "fieldtype": "Section Break",
                                "fieldname": fn,
                                "collapsible": False
                            })
                            current_section = q_section
                            
                        lbl = q.get("question", "")
                        
                        ft_slug = slugify("Long Text")
                        existing_fns = {f["fieldname"] for f in fields}
                        counter = 1
                        fn = f"{ft_slug}_{counter}"
                        while fn in existing_fns:
                            counter += 1
                            fn = f"{ft_slug}_{counter}"
                                
                        fields.append({
                            "label": lbl,
                            "fieldname": fn,
                            "fieldtype": "Long Text",
                            "options": "",
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
                            "description": q.get("question_code", ""),
                            "default": "",
                            "placeholder": ""
                        })
                        
                    return {
                        "job_id": job_id,
                        "status": "completed",
                        "document_name": checklist.get("document_name"),
                        "form_metadata": {
                            "fields": fields
                        }
                    }
