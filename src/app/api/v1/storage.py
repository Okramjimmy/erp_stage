"""
Storage API endpoints for MinIO file operations
"""

import logging
from typing import Optional
from fastapi import APIRouter, UploadFile, File, HTTPException, Response
from fastapi.responses import StreamingResponse
import io

from ...storage import storage_service
from src.config import settings
from urllib.parse import unquote

logger = logging.getLogger(__name__)
router = APIRouter()


@router.post("/upload")
async def upload_file(file: UploadFile = File(...), path: Optional[str] = None):
    """
    Upload a file to MinIO storage

    Args:
        file: The file to upload
        path: Optional path prefix for the file (e.g., "documents/", "images/")

    Returns:
        JSON response with upload status and file info
    """
    try:
        # Read file content
        file_content = await file.read()

        # Determine object name
        if path:
            # Ensure path ends with /
            path = path.rstrip('/') + '/'
            object_name = f"{path}{file.filename}"
        else:
            object_name = file.filename

        # Get content type
        content_type = file.content_type or "application/octet-stream"

        # Upload to MinIO
        success = storage_service.upload_file(
            file_data=file_content,
            object_name=object_name,
            content_type=content_type
        )

        if success:
            return {
                "status": "success",
                "message": "File uploaded successfully",
                "object_name": object_name,
                "size": len(file_content),
                "content_type": content_type
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to upload file to storage"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading file: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error uploading file: {str(e)}"
        )


@router.get("/list/{prefix:path}")
async def list_files(prefix: str = ""):
    """
    List files in MinIO storage with a given prefix

    Args:
        prefix: Path prefix to filter files

    Returns:
        List of file paths
    """
    try:
        files = storage_service.list_files(prefix)
        return {"files": files}
    except Exception as e:
        logger.error(f"Error listing files: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error listing files: {str(e)}"
        )


@router.get("/download/{file_path:path}")
async def download_file(file_path: str, download: int = 0):
    """
    Download a file from MinIO storage by accepting its complete path
    """
    try:
        from urllib.parse import unquote
        from datetime import timedelta
        from fastapi.responses import RedirectResponse
        
        # Decode path
        decoded_path = unquote(file_path)
        
        # Extract filename (last segment)
        filename = decoded_path.split('/')[-1] if '/' in decoded_path else decoded_path
        
        logger.info(f"Downloading/previewing file from MinIO: {decoded_path}")

        headers = {
            "response-content-disposition": f'inline; filename="{filename}"'
        }
        if download == 1:
            headers["response-content-disposition"] = f'attachment; filename="{filename}"'

        url = storage_service.generate_presigned_url(
            object_name=decoded_path,
            expires=timedelta(hours=1),
            response_headers=headers
        )

        if url:
            return RedirectResponse(url=url, status_code=307)
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to generate presigned URL"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error downloading file: {str(e)}"
        )


@router.delete("/delete/{file_name:path}")
async def delete_file(file_name: str):
    """
    Delete a file from MinIO storage

    Args:
        file_name: Name of the file to delete (including path)

    Returns:
        JSON response with deletion status
    """
    try:
        # Delete from MinIO
        success = storage_service.delete_file(file_name)

        if success:
            return {
                "status": "success",
                "message": "File deleted successfully",
                "object_name": file_name
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to delete file from storage"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting file: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting file: {str(e)}"
        )


@router.get("/list")
async def list_files(prefix: Optional[str] = None):
    """
    List files in MinIO storage

    Args:
        prefix: Optional path prefix to filter files

    Returns:
        JSON response with list of files
    """
    try:
        files = storage_service.list_files(prefix=prefix or "")

        return {
            "status": "success",
            "bucket": settings.minio_bucket_name,
            "prefix": prefix,
            "file_count": len(files),
            "files": files
        }
    except Exception as e:
        logger.error(f"Error listing files: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error listing files: {str(e)}"
        )


@router.get("/url/{file_name:path}")
async def get_file_url(file_name: str, expires_hours: int = 1):
    """
    Generate a presigned URL for file access

    Args:
        file_name: Name of the file (including path)
        expires_hours: Number of hours until the URL expires (default: 1)

    Returns:
        JSON response with presigned URL
    """
    try:
        from datetime import timedelta

        url = storage_service.generate_presigned_url(
            object_name=file_name,
            expires=timedelta(hours=expires_hours)
        )

        if url:
            return {
                "status": "success",
                "url": url,
                "expires_in_hours": expires_hours,
                "object_name": file_name
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Failed to generate presigned URL"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating URL: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Error generating URL: {str(e)}"
        )
