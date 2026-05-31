"""Storage module for object storage backends.

Provides abstract interface and implementations for MinIO, Azure Blob Storage,
and local filesystem storage for large evidence files.
"""

from app.storage.storage_client import StorageClient, get_storage_client
from app.storage.storage_config import StorageBackend, get_storage_backend

__all__ = [
    "StorageClient",
    "get_storage_client",
    "StorageBackend",
    "get_storage_backend",
]
