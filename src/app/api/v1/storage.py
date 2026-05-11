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


@router.get("/download/{file_name:path}")
async def download_file(file_name: str):
    """
    Download a file from MinIO storage

    Args:
        file_name: Name of the file to download (including path)

    Returns:
        File response with the file content
    """
    try:
        # FastAPI automatically decodes path parameters, so file_name is already decoded
        # MinIO stores files with actual characters (not URL-encoded), so we use it directly
        logger.info(f"Attempting to download file from MinIO: {file_name}")

        # Decode each path segment individually to match the stored path
        path_segments = file_name.split('/')
        decoded_path = '/'.join(unquote(segment) for segment in path_segments)
        logger.info(f"Decoded path for MinIO: {decoded_path}")
        

        file_content = storage_service.download_file(decoded_path)

        if file_content is None:
            logger.error(f"File not found in MinIO: {decoded_path}")
            raise HTTPException(
                status_code=404,
                detail="File not found"
            )

        logger.info(f"Successfully downloaded file: {decoded_path}")

        # Try to determine content type from file extension
        content_type = "application/octet-stream"
        if '.' in decoded_path:
            ext = decoded_path.rsplit('.', 1)[1].lower()
            content_types = {
                'txt': 'text/plain',
                'pdf': 'application/pdf',
                'jpg': 'image/jpeg',
                'jpeg': 'image/jpeg',
                'png': 'image/png',
                'gif': 'image/gif',
                'html': 'text/html',
                'json': 'application/json',
                'xml': 'application/xml'
            }
            content_type = content_types.get(ext, 'application/octet-stream')

        return Response(
            content=file_content,
            media_type=content_type,
            headers={
                "Content-Disposition": f"attachment; filename={decoded_path.split('/')[-1]}",
                "Content-Length": str(len(file_content))
            }
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
