"""
MinIO Storage Service
Handles file storage operations using MinIO S3-compatible storage
"""

from minio import Minio
from minio.error import S3Error
from minio.commonconfig import CopySource
from datetime import timedelta
import io
from typing import Optional, Tuple
from src.config import settings

class MinIOStorageService:
    def __init__(self):
        self.client = None
        self.bucket_name = settings.minio_bucket_name

    def connect(self):
        """Initialize MinIO client connection"""
        try:
            self.client = Minio(
                endpoint=settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure,
                region=settings.minio_default_region
            )
            return True
        except Exception as e:
            print(f"Failed to connect to MinIO: {e}")
            return False

    def ensure_bucket_exists(self) -> bool:
        """Create bucket if it doesn't exist"""
        try:
            if not self.client.bucket_exists(self.bucket_name):
                self.client.make_bucket(self.bucket_name)
                print(f"Created bucket: {self.bucket_name}")
            else:
                print(f"Bucket already exists: {self.bucket_name}")
            return True
        except S3Error as e:
            print(f"Error creating bucket: {e}")
            return False

    def upload_file(
        self,
        file_data: bytes,
        object_name: str,
        content_type: str = "application/octet-stream"
    ) -> bool:
        """
        Upload a file to MinIO

        Args:
            file_data: Raw bytes of the file to upload
            object_name: Name for the object in MinIO
            content_type: MIME type of the file

        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.put_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                data=io.BytesIO(file_data),
                length=len(file_data),
                content_type=content_type
            )
            return True
        except S3Error as e:
            print(f"Error uploading file: {e}")
            return False

    def download_file(self, object_name: str) -> Optional[bytes]:
        """
        Download a file from MinIO

        Args:
            object_name: Name of the object to download

        Returns:
            File data as bytes, or None if failed
        """
        try:
            print(f"MinIO: Attempting to download: {object_name}")
            response = self.client.get_object(
                bucket_name=self.bucket_name,
                object_name=object_name
            )
            data = response.read()
            print(f"MinIO: Successfully downloaded {len(data)} bytes")
            return data
        except S3Error as e:
            print(f"MinIO error downloading file '{object_name}': {e}")
            return None

    def delete_file(self, object_name: str) -> bool:
        """
        Delete a file from MinIO

        Args:
            object_name: Name of the object to delete

        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.remove_object(
                bucket_name=self.bucket_name,
                object_name=object_name
            )
            return True
        except S3Error as e:
            print(f"Error deleting file: {e}")
            return False

    def move_file(self, source_object_name: str, dest_object_name: str) -> bool:
        """
        Move a file from source to destination in MinIO

        Args:
            source_object_name: Current name of the object
            dest_object_name: New name for the object

        Returns:
            True if successful, False otherwise
        """
        try:
            if source_object_name == dest_object_name:
                return True
                
            self.client.copy_object(
                bucket_name=self.bucket_name,
                object_name=dest_object_name,
                source=CopySource(self.bucket_name, source_object_name)
            )
            self.client.remove_object(
                bucket_name=self.bucket_name,
                object_name=source_object_name
            )
            return True
        except S3Error as e:
            print(f"Error moving file: {e}")
            return False

    def generate_presigned_url(
        self,
        object_name: str,
        expires: timedelta = timedelta(hours=1)
    ) -> Optional[str]:
        """
        Generate a presigned URL for file access

        Args:
            object_name: Name of the object
            expires: URL expiration time

        Returns:
            Presigned URL, or None if failed
        """
        try:
            return self.client.presigned_get_object(
                bucket_name=self.bucket_name,
                object_name=object_name,
                expires=expires
            )
        except S3Error as e:
            print(f"Error generating presigned URL: {e}")
            return None

    def list_files(self, prefix: str = "") -> list:
        """
        List files in bucket with optional prefix filter

        Args:
            prefix: Filter objects by prefix

        Returns:
            List of object names
        """
        try:
            objects = self.client.list_objects(
                bucket_name=self.bucket_name,
                prefix=prefix
            )
            return [obj.object_name for obj in objects]
        except S3Error as e:
            print(f"Error listing files: {e}")
            return []


# Global storage service instance
storage_service = MinIOStorageService()


def init_storage():
    """Initialize storage service and ensure bucket exists"""
    if storage_service.connect():
        storage_service.ensure_bucket_exists()
        return True
    return False
