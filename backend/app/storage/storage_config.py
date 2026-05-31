"""Storage backend configuration."""

from enum import Enum

from app.core.config import get_settings


class StorageBackend(str, Enum):
    """Storage backend types."""

    LOCAL = "local"
    MINIO = "minio"
    AZURE_BLOB = "azure_blob"


def get_storage_backend() -> StorageBackend:
    """Get the configured storage backend from settings.

    Returns:
        StorageBackend enum value
    """
    settings = get_settings()
    backend = getattr(settings, "storage_backend", "local")
    return StorageBackend(backend)
