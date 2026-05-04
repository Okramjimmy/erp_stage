"""
Storage module initialization
"""

from .minio_storage import storage_service, init_storage

__all__ = ["storage_service", "init_storage"]
