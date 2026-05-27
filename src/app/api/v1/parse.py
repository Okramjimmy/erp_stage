"""Parse API endpoints."""

import os
import tempfile
from typing import List
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from src.app.core.auth import get_current_user
from src.app.database import get_db
from src.app.models.user import User
from src.app.services.parsing import ParsingService

router = APIRouter(prefix="/parse", tags=["Parse"])

@router.post("", response_model=dict)
async def parse_file(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """Parse a form with given data."""
    if current_user.user_id == "":
        raise HTTPException(status_code=401, detail="User not authenticated")
    
    # 1. Enforce max file size of 50MB
    MAX_SIZE = 50 * 1024 * 1024
    if file.size and file.size > MAX_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds the maximum limit of 50MB")
    
    file_content = await file.read()
    if len(file_content) > MAX_SIZE:
        raise HTTPException(status_code=400, detail="File size exceeds the maximum limit of 50MB")
    
    # Extract extension from original filename
    _, extension = os.path.splitext(file.filename)

    temp_file_path = ""

    # Create named temp file with same extension
    with tempfile.NamedTemporaryFile(
        suffix=extension,
        delete=False
    ) as temp_file:
        temp_file.write(file_content)
        temp_file.flush()
        temp_file_path = temp_file.name
        
    try:
        service = ParsingService(db)
        result = await service.parse_form(Path(temp_file_path))
    except Exception as e:
        print(f"Error parsing file: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Failed to parse file: {str(e)}")
    finally:
        # Cleanup temp file
        if temp_file_path and os.path.exists(temp_file_path):
            os.unlink(temp_file_path)

    return result
