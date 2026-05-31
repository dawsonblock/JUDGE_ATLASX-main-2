"""Tests for evidence store service.

Tests external filesystem storage for content-addressed snapshots.
"""

import hashlib
import os
import tempfile
from pathlib import Path

import pytest

from app.services.evidence_store import EvidenceStore


class TestEvidenceStore:
    """Test evidence store functionality."""

    def test_store_disabled_when_no_root(self):
        """Store should be disabled when no root path provided."""
        # Ensure env var is not set
        old_env = os.environ.pop("JTA_EVIDENCE_STORE_ROOT", None)
        try:
            store = EvidenceStore()
            assert not store.enabled
            assert store.root is None
        finally:
            if old_env:
                os.environ["JTA_EVIDENCE_STORE_ROOT"] = old_env

    def test_store_raises_on_nonexistent_path(self):
        """Store should raise RuntimeError when root path does not exist."""
        with pytest.raises(RuntimeError, match="does not exist"):
            EvidenceStore("/nonexistent/path/to/store")

    def test_store_raises_on_file_path(self):
        """Store should raise RuntimeError when path is a file, not a directory."""
        import tempfile
        with tempfile.NamedTemporaryFile() as f:
            with pytest.raises(RuntimeError, match="not a directory"):
                EvidenceStore(f.name)

    def test_store_enabled_with_existing_path(self):
        """Store should be enabled when path exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EvidenceStore(tmpdir)
            assert store.enabled
            assert store.root == Path(tmpdir).resolve()

    def test_write_snapshot_creates_correct_path(self):
        """Write should create content-addressed path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EvidenceStore(tmpdir)
            content = b"<html><body>Test content</body></html>"
            content_hash = hashlib.sha256(content).hexdigest()

            storage_path = store.write_snapshot(content, content_hash)

            assert storage_path is not None
            # Path format: snapshots/sha256/aa/bb/<hash>.bin
            assert storage_path.startswith("snapshots/sha256/")
            assert storage_path.endswith(f"{content_hash}.bin")

            # Verify file exists at expected location
            full_path = store.root / storage_path
            assert full_path.exists()

    def test_write_snapshot_content_verification(self):
        """Write should verify content matches hash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EvidenceStore(tmpdir)
            content = b"Test content"
            wrong_hash = "a" * 64  # Wrong hash

            with pytest.raises(ValueError, match="Hash mismatch"):
                store.write_snapshot(content, wrong_hash)

    def test_read_snapshot_retrieves_content(self):
        """Read should retrieve stored content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EvidenceStore(tmpdir)
            content = b"<html>Snapshot content</html>"
            content_hash = hashlib.sha256(content).hexdigest()

            storage_path = store.write_snapshot(content, content_hash)
            retrieved = store.read_snapshot(storage_path)

            assert retrieved == content

    def test_read_snapshot_returns_none_when_missing(self):
        """Read should return None for non-existent snapshot."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EvidenceStore(tmpdir)
            result = store.read_snapshot("snapshots/sha256/aa/bb/nonexistent.bin")
            assert result is None

    def test_read_snapshot_disabled_when_no_root(self):
        """Read should return None when store not enabled."""
        store = EvidenceStore(root_path=None)
        result = store.read_snapshot("any/path.bin")
        assert result is None

    def test_exists_returns_true_for_stored_content(self):
        """Exists should return True for stored content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EvidenceStore(tmpdir)
            content = b"Test content"
            content_hash = hashlib.sha256(content).hexdigest()

            assert not store.exists(content_hash)
            store.write_snapshot(content, content_hash)
            assert store.exists(content_hash)

    def test_exists_returns_false_for_missing_content(self):
        """Exists should return False for content not stored."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EvidenceStore(tmpdir)
            content_hash = "b" * 64
            assert not store.exists(content_hash)

    def test_write_snapshot_deduplication(self):
        """Writing same content twice should return same path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EvidenceStore(tmpdir)
            content = b"Duplicate content"
            content_hash = hashlib.sha256(content).hexdigest()

            path1 = store.write_snapshot(content, content_hash)
            path2 = store.write_snapshot(content, content_hash)

            assert path1 == path2
            # Should only have one file
            full_path = store.root / path1
            assert full_path.exists()

    def test_verify_snapshot_matches_hash(self):
        """Verify should return True for matching content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EvidenceStore(tmpdir)
            content = b"Verifiable content"
            content_hash = hashlib.sha256(content).hexdigest()

            storage_path = store.write_snapshot(content, content_hash)
            assert store.verify_snapshot(storage_path, content_hash)

    def test_verify_snapshot_fails_for_wrong_hash(self):
        """Verify should return False for wrong hash."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EvidenceStore(tmpdir)
            content = b"Content"
            content_hash = hashlib.sha256(content).hexdigest()
            wrong_hash = "c" * 64

            storage_path = store.write_snapshot(content, content_hash)
            assert not store.verify_snapshot(storage_path, wrong_hash)

    def test_verify_snapshot_fails_for_missing_file(self):
        """Verify should return False for missing file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EvidenceStore(tmpdir)
            assert not store.verify_snapshot("missing.bin", "d" * 64)

    def test_delete_snapshot_removes_file(self):
        """Delete should remove stored snapshot."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EvidenceStore(tmpdir)
            content = b"Deletable content"
            content_hash = hashlib.sha256(content).hexdigest()

            storage_path = store.write_snapshot(content, content_hash)
            full_path = store.root / storage_path

            assert full_path.exists()
            assert store.delete_snapshot(storage_path)
            assert not full_path.exists()

    def test_delete_snapshot_returns_true_for_missing(self):
        """Delete should return True for non-existent file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EvidenceStore(tmpdir)
            assert store.delete_snapshot("snapshots/sha256/aa/bb/missing.bin")

    def test_path_generation(self):
        """Path generation should follow aa/bb/<hash>.bin pattern."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EvidenceStore(tmpdir)
            content = b"Path test"
            content_hash = hashlib.sha256(content).hexdigest()

            storage_path = store.write_snapshot(content, content_hash)

            # Extract components
            parts = storage_path.split("/")
            assert len(parts) == 5
            assert parts[0] == "snapshots"
            assert parts[1] == "sha256"
            assert parts[2] == content_hash[:2]  # First 2 chars
            assert parts[3] == content_hash[2:4]  # Next 2 chars
            assert parts[4] == f"{content_hash}.bin"

    def test_store_from_env_var(self):
        """Store should read root path from env var."""
        with tempfile.TemporaryDirectory() as tmpdir:
            old_env = os.environ.get("JTA_EVIDENCE_STORE_ROOT")
            os.environ["JTA_EVIDENCE_STORE_ROOT"] = tmpdir
            try:
                store = EvidenceStore()  # No arg, reads from env
                assert store.enabled
                assert store.root == Path(tmpdir).resolve()
            finally:
                if old_env:
                    os.environ["JTA_EVIDENCE_STORE_ROOT"] = old_env
                else:
                    os.environ.pop("JTA_EVIDENCE_STORE_ROOT", None)

    def test_hash_length_validation(self):
        """Store should reject invalid hash lengths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EvidenceStore(tmpdir)
            content = b"Test"

            with pytest.raises(ValueError):
                store.write_snapshot(content, "tooshort")

            with pytest.raises(ValueError):
                store._get_storage_path("tooshort")

    def test_large_content_storage(self):
        """Store should handle larger content correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EvidenceStore(tmpdir)
            content = b"<html>" + b"A" * 100000 + b"</html>"  # ~100KB
            content_hash = hashlib.sha256(content).hexdigest()

            storage_path = store.write_snapshot(content, content_hash)
            retrieved = store.read_snapshot(storage_path)

            assert retrieved == content
            assert len(retrieved) == len(content)

    def test_write_snapshot_raises_oserror_on_post_write_hash_mismatch(self):
        """write_snapshot should raise OSError when on-disk bytes don't match the expected hash."""
        import pathlib
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            store = EvidenceStore(tmpdir)
            content = b"<html>valid content</html>"
            content_hash = hashlib.sha256(content).hexdigest()

            def patched_read(self_path):
                return b"corrupted data on disk"

            with patch.object(pathlib.Path, "read_bytes", patched_read):
                with pytest.raises(OSError, match="SHA-256 mismatch after write"):
                    store.write_snapshot(content, content_hash)

    def test_write_snapshot_raises_oserror_on_zero_byte_read_after_write(self):
        """write_snapshot raises OSError (hash mismatch) when disk returns empty bytes."""
        import pathlib
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            store = EvidenceStore(tmpdir)
            content = b"<html>valid content</html>"
            content_hash = hashlib.sha256(content).hexdigest()

            with patch.object(pathlib.Path, "read_bytes", return_value=b""):
                with pytest.raises(OSError, match="SHA-256 mismatch after write"):
                    store.write_snapshot(content, content_hash)

    def test_write_snapshot_accepts_empty_content(self):
        """write_snapshot stores empty bytes when the provided hash matches sha256 of b''."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EvidenceStore(tmpdir)
            content = b""
            content_hash = hashlib.sha256(content).hexdigest()
            storage_path = store.write_snapshot(content, content_hash)
            assert storage_path is not None
            assert store.read_snapshot(storage_path) == b""

    # ---------------------------------------------------------------------------
    # Path traversal protection tests
    # ---------------------------------------------------------------------------

    def test_read_snapshot_parent_traversal_raises(self):
        """read_snapshot must reject paths that escape the evidence root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EvidenceStore(tmpdir)
            with pytest.raises(OSError, match="escapes evidence root"):
                store.read_snapshot("../outside.bin")

    def test_read_snapshot_absolute_path_raises(self):
        """read_snapshot must reject absolute paths."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EvidenceStore(tmpdir)
            with pytest.raises(OSError, match="escapes evidence root"):
                store.read_snapshot("/etc/passwd")

    def test_delete_snapshot_parent_traversal_raises(self):
        """delete_snapshot must reject paths that escape the evidence root."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = EvidenceStore(tmpdir)
            with pytest.raises(OSError, match="escapes evidence root"):
                store.delete_snapshot("../../parent.bin")
