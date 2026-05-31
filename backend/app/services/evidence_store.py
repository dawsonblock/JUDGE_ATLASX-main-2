"""External evidence storage service for content-addressed snapshots.

Supports storing raw snapshot content on filesystem (e.g., external hard drive)
while keeping metadata in the database. Uses SHA256 content hashing for
content-addressed storage and deduplication.

Environment:
    JTA_EVIDENCE_STORE_ROOT: Root directory for evidence storage.
        If unset, snapshots stored in DB (existing behavior).
        If set, snapshots stored at:
            {root}/snapshots/sha256/aa/bb/<full_hash>.bin

Example:
    >>> store = EvidenceStore()
    >>> content = b"<html>...</html>"
    >>> hash_val = hashlib.sha256(content).hexdigest()
    >>> path = store.write_snapshot(content, hash_val)
    >>> # Returns: "snapshots/sha256/ab/cd/abcdef1234...89.bin"
    >>> retrieved = store.read_snapshot(path)
"""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

# Strict SHA-256 format: exactly 64 lowercase hex characters.
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class EvidenceStore:
    """Content-addressed evidence storage with SHA256 hashing.

    Stores raw content on filesystem organized by hash prefix for
    efficient lookup. Falls back to DB storage when JTA_EVIDENCE_STORE_ROOT
    is not configured.
    """

    def __init__(self, root_path: str | None = None) -> None:
        """Initialize evidence store.

        Args:
            root_path: Root directory for storage. If None, reads from
                JTA_EVIDENCE_STORE_ROOT env var.

        Raises:
            RuntimeError: If root_path is explicitly configured but does not exist
        """
        if root_path is None:
            root_path = os.getenv("JTA_EVIDENCE_STORE_ROOT")

        if root_path:
            candidate = Path(root_path).expanduser().resolve()
            if not candidate.exists():
                raise RuntimeError(
                    f"JTA_EVIDENCE_STORE_ROOT does not exist: {candidate}"
                )
            if not candidate.is_dir():
                raise RuntimeError(
                    f"JTA_EVIDENCE_STORE_ROOT is not a directory: {candidate}"
                )
            if not os.access(candidate, os.W_OK):
                raise RuntimeError(
                    f"JTA_EVIDENCE_STORE_ROOT is not writable: {candidate}"
                )
            self.root = candidate
            self._enabled = True
        else:
            self.root = None
            self._enabled = False

    @property
    def enabled(self) -> bool:
        """Whether external storage is enabled and accessible."""
        return self._enabled

    def _get_storage_path(self, content_hash: str) -> Path | None:
        """Generate filesystem path for a content hash.

        Path format: snapshots/sha256/aa/bb/<full_hash>.bin
        where aa = first 2 chars, bb = next 2 chars of hash.

        Args:
            content_hash: SHA256 hex digest

        Returns:
            Full storage path, or None if external storage not enabled
        """
        if not self.root:
            return None

        if not _SHA256_RE.match(content_hash):
            raise ValueError(
                f"Invalid SHA-256 hash (must be 64 lowercase hex chars): {content_hash!r}"
            )

        aa = content_hash[:2]
        bb = content_hash[2:4]
        filename = f"{content_hash}.bin"

        return self.root / "snapshots" / "sha256" / aa / bb / filename

    def _get_relative_path(self, content_hash: str) -> str:
        """Get relative storage path string for database storage.

        Args:
            content_hash: SHA256 hex digest

        Returns:
            Relative path string like "snapshots/sha256/aa/bb/hash.bin"
        """
        if not _SHA256_RE.match(content_hash):
            raise ValueError(
                f"Invalid SHA-256 hash (must be 64 lowercase hex chars): {content_hash!r}"
            )

        aa = content_hash[:2]
        bb = content_hash[2:4]
        filename = f"{content_hash}.bin"

        return f"snapshots/sha256/{aa}/{bb}/{filename}"

    def write_snapshot(self, content: bytes, content_hash: str) -> str | None:
        """Write snapshot content to external storage.

        Args:
            content: Raw bytes to store
            content_hash: SHA256 hex digest of content (for verification)

        Returns:
            Relative storage path if written successfully, None if external
            storage not enabled or hash mismatch.

        Raises:
            ValueError: If content hash doesn't match computed hash
            IOError: If write fails
        """
        if not self.root:
            return None

        # Validate SHA-256 format (64 lowercase hex chars)
        if not _SHA256_RE.match(content_hash):
            raise ValueError(
                f"Invalid SHA-256 hash (must be 64 lowercase hex chars): {content_hash!r}"
            )

        # Verify hash matches content
        computed_hash = hashlib.sha256(content).hexdigest()
        if computed_hash != content_hash:
            raise ValueError(
                f"Hash mismatch: provided {content_hash}, computed {computed_hash}"
            )

        # Check for deduplication
        storage_path = self._get_storage_path(content_hash)
        if storage_path and storage_path.exists():
            # Re-verify the existing file's integrity before trusting the dedup hit.
            # A corrupted or misplaced file would silently return bad provenance data.
            try:
                existing_bytes = storage_path.read_bytes()
                existing_hash = hashlib.sha256(existing_bytes).hexdigest()
            except OSError:
                existing_hash = ""  # force overwrite on unreadable file
            if existing_hash == content_hash:
                return self._get_relative_path(content_hash)
            # Hash mismatch — fall through to overwrite the corrupt file.

        # Create directory structure and write atomically via temp file + rename
        if storage_path:
            storage_path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_path = tempfile.mkstemp(
                dir=str(storage_path.parent), prefix=".tmp_", suffix=".bin"
            )
            try:
                os.write(fd, content)
                os.fsync(fd)
                os.close(fd)
                os.replace(tmp_path, storage_path)
                # Post-write integrity verification
                if not storage_path.exists():
                    raise IOError(
                        f"Write verification failed: file missing after atomic rename: {storage_path}"
                    )
                if content and storage_path.stat().st_size == 0:
                    raise IOError(
                        f"Write verification failed: zero-byte file after atomic rename: {storage_path}"
                    )
                written = storage_path.read_bytes()
                if hashlib.sha256(written).hexdigest() != content_hash:
                    raise IOError(
                        f"Write verification failed: SHA-256 mismatch after write for {content_hash}"
                    )
            except BaseException:
                try:
                    os.close(fd)
                except OSError:
                    pass
                Path(tmp_path).unlink(missing_ok=True)
                raise

        return self._get_relative_path(content_hash)

    def read_snapshot(self, storage_path: str) -> bytes | None:
        """Read snapshot content from external storage.

        Args:
            storage_path: Relative path as stored in database
                (e.g., "snapshots/sha256/aa/bb/hash.bin")

        Returns:
            Content bytes if found, None otherwise
        """
        if not self.root:
            return None

        root = self.root.resolve()
        full_path = (self.root / storage_path).resolve()
        if not full_path.is_relative_to(root):
            raise OSError(
                f"Snapshot storage path escapes evidence root: {storage_path!r}"
            )
        if not full_path.exists():
            return None

        return full_path.read_bytes()

    def exists(self, content_hash: str) -> bool:
        """Check if content already exists in external storage.

        Args:
            content_hash: SHA256 hex digest to check

        Returns:
            True if content exists in external storage
        """
        if not self.root:
            return False

        storage_path = self._get_storage_path(content_hash)
        if not storage_path:
            return False

        return storage_path.exists()

    def delete_snapshot(self, storage_path: str) -> bool:
        """Delete snapshot from external storage.

        Args:
            storage_path: Relative path to delete

        Returns:
            True if deleted or not found, False on error
        """
        if not self.root:
            return False

        root = self.root.resolve()
        full_path = (self.root / storage_path).resolve()
        if not full_path.is_relative_to(root):
            raise OSError(
                f"Snapshot storage path escapes evidence root: {storage_path!r}"
            )
        if not full_path.exists():
            return True

        try:
            full_path.unlink()
            # Clean up empty parent directories
            parent = full_path.parent
            while parent != root:
                try:
                    parent.rmdir()
                    parent = parent.parent
                except OSError:
                    break
            return True
        except OSError:
            return False

    def verify_snapshot(self, storage_path: str, expected_hash: str) -> bool:
        """Verify stored content matches expected hash.

        Args:
            storage_path: Relative path to verify
            expected_hash: Expected SHA256 hex digest

        Returns:
            True if content exists and hash matches
        """
        content = self.read_snapshot(storage_path)
        if content is None:
            return False

        computed_hash = hashlib.sha256(content).hexdigest()
        return computed_hash == expected_hash
