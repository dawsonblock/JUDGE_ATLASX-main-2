"""Tests for snapshot_writer evidence integrity contract.

Proves:
1. Small snapshot stores full DB content and hash verifies
2. Oversized snapshot without evidence store raises ValueError (never partial)
3. Oversized snapshot with evidence store succeeds and hash verifies
4. No test allows silent truncation
5. stored_content_hash == original_content_hash on every successful write
6. is_truncated is always False after a successful write
"""
from __future__ import annotations

import hashlib
import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import Base
from app.models.entities import SourceSnapshot
from app.services.snapshot_writer import MAX_DB_SIZE, write_snapshot


@pytest.fixture()
def db():
    """In-memory SQLite session with the full schema."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    # SQLite FK support
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, _):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def _ts() -> datetime:
    return datetime.now(timezone.utc)


class TestSmallSnapshot:
    """Content that fits inside MAX_DB_SIZE stores entirely in DB."""

    def test_small_content_stored_in_db(self, db):
        content = b"<html><body>small content</body></html>"
        snap = write_snapshot(db, "http://example.com/page", _ts(), content)
        assert snap.storage_backend == "db"
        assert snap.raw_content is not None

    def test_small_content_hash_integrity(self, db):
        content = b"<html>hello world</html>"
        expected_hash = hashlib.sha256(content).hexdigest()
        snap = write_snapshot(db, "http://example.com/", _ts(), content)
        assert snap.content_hash == expected_hash
        assert snap.original_content_hash == expected_hash
        assert snap.stored_content_hash == expected_hash

    def test_small_content_stored_hash_matches_stored_bytes(self, db):
        content = b"Test content for hash verification."
        snap = write_snapshot(db, "http://example.com/", _ts(), content)
        db.flush()
        # Re-read stored raw_content and verify its hash
        stored_bytes = snap.raw_content.encode("utf-8")
        computed = hashlib.sha256(stored_bytes).hexdigest()
        assert computed == snap.stored_content_hash, (
            "stored_content_hash does not match stored raw_content"
        )

    def test_small_snapshot_is_not_truncated(self, db):
        content = b"Small content."
        snap = write_snapshot(db, "http://example.com/", _ts(), content)
        assert snap.is_truncated is False

    def test_small_snapshot_size_metadata(self, db):
        content = b"X" * 100
        snap = write_snapshot(db, "http://example.com/", _ts(), content)
        assert snap.content_size_bytes == 100
        assert snap.stored_size_bytes == 100

    def test_string_content_same_as_bytes(self, db):
        content_str = "<html>string content</html>"
        content_bytes = content_str.encode("utf-8")
        expected_hash = hashlib.sha256(content_bytes).hexdigest()
        snap = write_snapshot(db, "http://example.com/", _ts(), content_str)
        assert snap.content_hash == expected_hash
        assert snap.stored_content_hash == expected_hash


class TestOversizedWithoutEvidenceStore:
    """Oversized content without evidence store MUST raise ValueError, never create partial."""

    def test_oversized_without_store_raises(self, db):
        oversized = b"A" * (MAX_DB_SIZE + 1)
        with patch.dict(os.environ, {}, clear=True):
            # Ensure JTA_EVIDENCE_STORE_ROOT is not set
            os.environ.pop("JTA_EVIDENCE_STORE_ROOT", None)
            with pytest.raises(ValueError, match="MAX_DB_SIZE"):
                write_snapshot(db, "http://example.com/big", _ts(), oversized)

    def test_oversized_without_store_does_not_add_to_session(self, db):
        oversized = b"B" * (MAX_DB_SIZE + 1)
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("JTA_EVIDENCE_STORE_ROOT", None)
            try:
                write_snapshot(db, "http://example.com/big", _ts(), oversized)
            except ValueError:
                pass
        # Nothing should be pending in the session
        assert len(db.new) == 0

    def test_exactly_max_db_size_is_allowed(self, db):
        """Content exactly at the limit should fit in DB (boundary test)."""
        content = b"C" * MAX_DB_SIZE
        snap = write_snapshot(db, "http://example.com/", _ts(), content)
        assert snap.storage_backend == "db"
        assert snap.is_truncated is False

    def test_one_byte_over_max_raises(self, db):
        """One byte over the limit must raise ValueError."""
        content = b"D" * (MAX_DB_SIZE + 1)
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("JTA_EVIDENCE_STORE_ROOT", None)
            with pytest.raises(ValueError):
                write_snapshot(db, "http://example.com/", _ts(), content)


class TestOversizedWithEvidenceStore:
    """Oversized content with evidence store stores in filesystem and hash verifies."""

    @pytest.fixture(autouse=True)
    def _reset_settings_cache(self):
        """Clear the lru_cache before and after each test so env patches are visible."""
        get_settings.cache_clear()
        yield
        get_settings.cache_clear()

    def test_oversized_with_store_succeeds(self, db):
        with tempfile.TemporaryDirectory() as tmpdir:
            oversized = b"E" * (MAX_DB_SIZE + 1)
            with patch.dict(os.environ, {"JTA_EVIDENCE_STORE_ROOT": tmpdir}):
                get_settings.cache_clear()
                snap = write_snapshot(db, "http://example.com/big", _ts(), oversized)
            assert snap.storage_backend == "filesystem"
            assert snap.storage_path is not None
            assert snap.raw_content is None  # Not duplicated in DB

    def test_oversized_with_store_hash_integrity(self, db):
        with tempfile.TemporaryDirectory() as tmpdir:
            oversized = b"F" * (MAX_DB_SIZE + 1)
            expected_hash = hashlib.sha256(oversized).hexdigest()
            with patch.dict(os.environ, {"JTA_EVIDENCE_STORE_ROOT": tmpdir}):
                get_settings.cache_clear()
                snap = write_snapshot(db, "http://example.com/big", _ts(), oversized)
            assert snap.content_hash == expected_hash
            assert snap.original_content_hash == expected_hash
            assert snap.stored_content_hash == expected_hash

    def test_oversized_with_store_not_truncated(self, db):
        with tempfile.TemporaryDirectory() as tmpdir:
            oversized = b"G" * (MAX_DB_SIZE + 1)
            with patch.dict(os.environ, {"JTA_EVIDENCE_STORE_ROOT": tmpdir}):
                get_settings.cache_clear()
                snap = write_snapshot(db, "http://example.com/big", _ts(), oversized)
            assert snap.is_truncated is False

    def test_oversized_with_store_size_metadata(self, db):
        with tempfile.TemporaryDirectory() as tmpdir:
            size = MAX_DB_SIZE + 500
            oversized = b"H" * size
            with patch.dict(os.environ, {"JTA_EVIDENCE_STORE_ROOT": tmpdir}):
                get_settings.cache_clear()
                snap = write_snapshot(db, "http://example.com/big", _ts(), oversized)
            assert snap.content_size_bytes == size
            assert snap.stored_size_bytes == size

    def test_file_stored_in_evidence_store_matches_hash(self, db):
        with tempfile.TemporaryDirectory() as tmpdir:
            oversized = b"I" * (MAX_DB_SIZE + 1)
            expected_hash = hashlib.sha256(oversized).hexdigest()
            with patch.dict(os.environ, {"JTA_EVIDENCE_STORE_ROOT": tmpdir}):
                get_settings.cache_clear()
                snap = write_snapshot(db, "http://example.com/big", _ts(), oversized)
            # Verify file on disk
            from app.services.evidence_store import EvidenceStore
            store = EvidenceStore(tmpdir)
            assert store.verify_snapshot(snap.storage_path, expected_hash)


class TestNoSilentTruncation:
    """Regression tests: ensure no code path silently truncates evidence."""

    def test_content_hash_never_computed_on_truncated_content(self, db):
        """The hash must be of the full content, not a truncated slice."""
        content = b"J" * MAX_DB_SIZE
        snap = write_snapshot(db, "http://example.com/", _ts(), content)
        full_hash = hashlib.sha256(content).hexdigest()
        # If content were truncated before hashing, hash would differ
        assert snap.content_hash == full_hash
        assert snap.original_content_hash == full_hash

    def test_extractor_metadata_stored(self, db):
        content = b"<html>extractor test</html>"
        snap = write_snapshot(
            db, "http://example.com/", _ts(), content,
            extractor_name="html_parser",
            extractor_version="stdlib",
        )
        assert snap.extractor_name == "html_parser"
        assert snap.extractor_version == "stdlib"


class TestBinaryContentRoundTrip:
    """Binary content (e.g. PDFs) must be stored and retrieved without data loss."""

    def test_binary_content_stored_losslessly(self, db):
        """Arbitrary binary bytes round-trip through DB without modification."""
        # Bytes that are NOT valid UTF-8
        binary = bytes(range(256))
        snap = write_snapshot(db, "http://example.com/bin", _ts(), binary)
        assert snap.storage_backend == "db"
        # raw_content should be the base64-encoded form
        assert snap.raw_content is not None
        assert snap.raw_content.startswith("base64:")

    def test_binary_content_hash_integrity(self, db):
        """Stored hash matches the original binary bytes."""
        binary = bytes(range(256))
        expected_hash = hashlib.sha256(binary).hexdigest()
        snap = write_snapshot(db, "http://example.com/bin", _ts(), binary)
        assert snap.original_content_hash == expected_hash
        assert snap.stored_content_hash == expected_hash

    def test_read_snapshot_content_recovers_binary(self, db):
        """read_snapshot_content returns original binary bytes from DB storage."""
        from app.services.snapshot_writer import read_snapshot_content
        binary = bytes(range(256))
        snap = write_snapshot(db, "http://example.com/bin", _ts(), binary)
        db.flush()
        recovered = read_snapshot_content(db, snap)
        assert recovered == binary, "read_snapshot_content must recover original binary bytes"

    def test_read_snapshot_content_recovers_text(self, db):
        """read_snapshot_content returns correct bytes for plain text content."""
        from app.services.snapshot_writer import read_snapshot_content
        content = b"<html>Hello world</html>"
        snap = write_snapshot(db, "http://example.com/", _ts(), content)
        db.flush()
        recovered = read_snapshot_content(db, snap)
        assert recovered == content

    def test_stored_hash_matches_recovered_bytes(self, db):
        """Hash of recovered bytes must equal stored_content_hash for both text and binary."""
        from app.services.snapshot_writer import read_snapshot_content
        for content in [b"plain UTF-8 text", bytes(range(256)), b"\xff\xfe binary \x00"]:
            snap = write_snapshot(db, "http://example.com/", _ts(), content)
            db.flush()
            recovered = read_snapshot_content(db, snap)
            assert recovered is not None
            assert hashlib.sha256(recovered).hexdigest() == snap.stored_content_hash, (
                f"Hash mismatch for content starting with {content[:8]!r}"
            )
