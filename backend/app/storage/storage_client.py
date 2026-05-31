"""Storage client interface and implementations.

Provides abstract interface for object storage backends
and concrete implementations for local, MinIO, and Azure Blob Storage.
"""

from __future__ import annotations

import hashlib
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import BinaryIO

from app.storage.storage_config import StorageBackend, get_storage_backend


class StorageClient(ABC):
    """Abstract interface for object storage backends."""

    @abstractmethod
    def put(
        self,
        key: str,
        data: bytes | BinaryIO,
        content_type: str | None = None,
    ) -> str:
        """Store data in object storage.

        Args:
            key: Storage key/path
            data: Data to store (bytes or file-like object)
            content_type: MIME content type

        Returns:
            Storage URI or key
        """

    @abstractmethod
    def get(self, key: str) -> bytes:
        """Retrieve data from object storage.

        Args:
            key: Storage key/path

        Returns:
            Stored data as bytes

        Raises:
            FileNotFoundError: If key does not exist
        """

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Check if key exists in storage.

        Args:
            key: Storage key/path

        Returns:
            True if exists, False otherwise
        """

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete data from object storage.

        Args:
            key: Storage key/path

        Returns:
            True if successful, False otherwise
        """

    @abstractmethod
    def get_url(self, key: str, expires_in: int = 3600) -> str:
        """Get presigned URL for temporary access.

        Args:
            key: Storage key/path
            expires_in: URL expiration time in seconds

        Returns:
            Presigned URL
        """

    def compute_hash(self, data: bytes) -> str:
        """Compute SHA256 hash of data.

        Args:
            data: Data to hash

        Returns:
            Hexadecimal hash string
        """
        return hashlib.sha256(data).hexdigest()


class LocalStorageClient(StorageClient):
    """Local filesystem storage implementation."""

    def __init__(self, base_path: str | None = None):
        """Initialize local storage client.

        Args:
            base_path: Base directory for storage
        """
        if base_path is None:
            base_path = os.environ.get("JTA_STORAGE_LOCAL_PATH", "./storage")
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def _get_path(self, key: str) -> Path:
        """Get filesystem path for key.

        Args:
            key: Storage key

        Returns:
            Filesystem path
        """
        if not key:
            raise ValueError("Storage key must be non-empty")

        key_path = Path(key)
        if key_path.is_absolute():
            raise ValueError("Storage key must be relative")

        base_resolved = self.base_path.resolve()
        candidate = (base_resolved / key_path).resolve()
        try:
            candidate.relative_to(base_resolved)
        except ValueError as exc:
            raise ValueError("Storage key escapes storage root") from exc
        return candidate

    def put(
        self,
        key: str,
        data: bytes | BinaryIO,
        content_type: str | None = None,
    ) -> str:
        """Store data in local filesystem.

        Args:
            key: Storage key/path
            data: Data to store
            content_type: MIME content type (ignored for local)

        Returns:
            File path
        """
        path = self._get_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)

        mode = "wb" if isinstance(data, bytes) else "wb"
        with open(path, mode) as f:
            if isinstance(data, bytes):
                f.write(data)
            else:
                f.write(data.read())

        return str(path)

    def get(self, key: str) -> bytes:
        """Retrieve data from local filesystem.

        Args:
            key: Storage key/path

        Returns:
            Stored data as bytes

        Raises:
            FileNotFoundError: If key does not exist
        """
        path = self._get_path(key)
        if not path.exists():
            raise FileNotFoundError(f"Key not found: {key}")
        with open(path, "rb") as f:
            return f.read()

    def exists(self, key: str) -> bool:
        """Check if key exists in local filesystem.

        Args:
            key: Storage key/path

        Returns:
            True if exists, False otherwise
        """
        return self._get_path(key).exists()

    def delete(self, key: str) -> bool:
        """Delete data from local filesystem.

        Args:
            key: Storage key/path

        Returns:
            True if successful, False otherwise
        """
        path = self._get_path(key)
        if path.exists():
            path.unlink()
            return True
        return False

    def get_url(self, key: str, expires_in: int = 3600) -> str:
        """Get file URL (not presigned for local).

        Args:
            key: Storage key/path
            expires_in: URL expiration (ignored for local)

        Returns:
            File URL (file://)
        """
        path = self._get_path(key)
        return f"file://{path.absolute()}"


class MinIOStorageClient(StorageClient):
    """MinIO S3-compatible storage implementation.

    Falls back to local storage if MinIO unavailable.
    """

    def __init__(self):
        """Initialize MinIO storage client."""
        self._client = None
        self._bucket = os.environ.get(
            "JTA_STORAGE_MINIO_BUCKET", "judge-atlasx"
        )
        self._endpoint = os.environ.get(
            "JTA_STORAGE_MINIO_ENDPOINT", "localhost:9000"
        )
        self._access_key = os.environ.get(
            "JTA_STORAGE_MINIO_ACCESS_KEY", "minioadmin"
        )
        self._secret_key = os.environ.get(
            "JTA_STORAGE_MINIO_SECRET_KEY", "minioadmin"
        )
        self._secure = os.environ.get(
            "JTA_STORAGE_MINIO_SECURE", "false"
        ).lower() == "true"

        try:
            from minio import Minio

            self._client = Minio(
                self._endpoint,
                access_key=self._access_key,
                secret_key=self._secret_key,
                secure=self._secure,
            )
            # Create bucket if it doesn't exist
            if not self._client.bucket_exists(self._bucket):
                self._client.make_bucket(self._bucket)
        except Exception:
            # Fall back to local storage if MinIO unavailable
            self._client = None

    def put(
        self,
        key: str,
        data: bytes | BinaryIO,
        content_type: str | None = None,
    ) -> str:
        """Store data in MinIO.

        Args:
            key: Storage key/path
            data: Data to store
            content_type: MIME content type

        Returns:
            Storage key
        """
        if self._client is None:
            # Fall back to local storage
            return LocalStorageClient().put(key, data, content_type)

        length = len(data) if isinstance(data, bytes) else -1
        self._client.put_object(
            self._bucket,
            key,
            data if isinstance(data, bytes) else data,
            length=length,
            content_type=content_type,
        )
        return key

    def get(self, key: str) -> bytes:
        """Retrieve data from MinIO.

        Args:
            key: Storage key/path

        Returns:
            Stored data as bytes

        Raises:
            FileNotFoundError: If key does not exist
        """
        if self._client is None:
            # Fall back to local storage
            return LocalStorageClient().get(key)

        try:
            response = self._client.get_object(self._bucket, key)
            return response.read()
        except Exception as e:
            raise FileNotFoundError(f"Key not found: {key}") from e

    def exists(self, key: str) -> bool:
        """Check if key exists in MinIO.

        Args:
            key: Storage key/path

        Returns:
            True if exists, False otherwise
        """
        if self._client is None:
            # Fall back to local storage
            return LocalStorageClient().exists(key)

        try:
            self._client.stat_object(self._bucket, key)
            return True
        except Exception:
            return False

    def delete(self, key: str) -> bool:
        """Delete data from MinIO.

        Args:
            key: Storage key/path

        Returns:
            True if successful, False otherwise
        """
        if self._client is None:
            # Fall back to local storage
            return LocalStorageClient().delete(key)

        try:
            self._client.remove_object(self._bucket, key)
            return True
        except Exception:
            return False

    def get_url(self, key: str, expires_in: int = 3600) -> str:
        """Get presigned URL for MinIO.

        Args:
            key: Storage key/path
            expires_in: URL expiration time in seconds

        Returns:
            Presigned URL
        """
        if self._client is None:
            # Fall back to local storage
            return LocalStorageClient().get_url(key, expires_in)

        return self._client.presigned_get_object(
            self._bucket, key, expires=expires_in
        )


class AzureBlobStorageClient(StorageClient):
    """Azure Blob Storage implementation.

    Falls back to local storage if Azure unavailable.
    """

    def __init__(self):
        """Initialize Azure Blob Storage client."""
        self._client = None
        self._container_name = os.environ.get(
            "JTA_STORAGE_AZURE_CONTAINER", "judge-atlasx"
        )
        self._connection_string = os.environ.get(
            "JTA_STORAGE_AZURE_CONNECTION_STRING"
        )

        try:
            from azure.storage.blob import BlobServiceClient

            self._client = BlobServiceClient.from_connection_string(
                self._connection_string
            )
            # Create container if it doesn't exist
            container_client = self._client.get_container_client(
                self._container_name
            )
            if not container_client.exists():
                container_client.create_container()
        except Exception:
            # Fall back to local storage if Azure unavailable
            self._client = None

    def put(
        self,
        key: str,
        data: bytes | BinaryIO,
        content_type: str | None = None,
    ) -> str:
        """Store data in Azure Blob Storage.

        Args:
            key: Storage key/path
            data: Data to store
            content_type: MIME content type

        Returns:
            Blob name
        """
        if self._client is None:
            # Fall back to local storage
            return LocalStorageClient().put(key, data, content_type)

        blob_client = self._client.get_blob_client(
            self._container_name, key
        )
        blob_client.upload_blob(
            data if isinstance(data, bytes) else data.read(),
            overwrite=True,
            content_settings=(
                {"content_type": content_type} if content_type else None
            ),
        )
        return key

    def get(self, key: str) -> bytes:
        """Retrieve data from Azure Blob Storage.

        Args:
            key: Storage key/path

        Returns:
            Stored data as bytes

        Raises:
            FileNotFoundError: If key does not exist
        """
        if self._client is None:
            # Fall back to local storage
            return LocalStorageClient().get(key)

        try:
            blob_client = self._client.get_blob_client(
                self._container_name, key
            )
            blob_data = blob_client.download_blob()
            return blob_data.readall()
        except Exception as e:
            raise FileNotFoundError(f"Key not found: {key}") from e

    def exists(self, key: str) -> bool:
        """Check if key exists in Azure Blob Storage.

        Args:
            key: Storage key/path

        Returns:
            True if exists, False otherwise
        """
        if self._client is None:
            # Fall back to local storage
            return LocalStorageClient().exists(key)

        try:
            blob_client = self._client.get_blob_client(
                self._container_name, key
            )
            return blob_client.exists()
        except Exception:
            return False

    def delete(self, key: str) -> bool:
        """Delete data from Azure Blob Storage.

        Args:
            key: Storage key/path

        Returns:
            True if successful, False otherwise
        """
        if self._client is None:
            # Fall back to local storage
            return LocalStorageClient().delete(key)

        try:
            blob_client = self._client.get_blob_client(
                self._container_name, key
            )
            blob_client.delete_blob()
            return True
        except Exception:
            return False

    def get_url(self, key: str, expires_in: int = 3600) -> str:
        """Get SAS URL for Azure Blob Storage.

        Args:
            key: Storage key/path
            expires_in: URL expiration time in seconds

        Returns:
            SAS URL
        """
        if self._client is None:
            # Fall back to local storage
            return LocalStorageClient().get_url(key, expires_in)

        from azure.storage.blob import generate_blob_sas, BlobSasPermissions
        from datetime import datetime, timedelta, timezone

        blob_client = self._client.get_blob_client(
            self._container_name, key
        )
        sas_token = generate_blob_sas(
            account_name=self._client.account_name,
            container_name=self._container_name,
            blob_name=key,
            account_key=self._client.credential.account_key,
            permission=BlobSasPermissions(read=True),
            expiry=datetime.now(timezone.utc) + timedelta(
                seconds=expires_in
            ),
        )
        return f"{blob_client.url}?{sas_token}"


# Shared storage client instance
_storage_client: StorageClient | None = None


def get_storage_client() -> StorageClient:
    """Get or create the shared storage client instance.

    Returns:
        Storage client instance based on configured backend
    """
    global _storage_client
    if _storage_client is None:
        backend = get_storage_backend()
        if backend == StorageBackend.MINIO:
            _storage_client = MinIOStorageClient()
        elif backend == StorageBackend.AZURE_BLOB:
            _storage_client = AzureBlobStorageClient()
        else:
            _storage_client = LocalStorageClient()
    return _storage_client
