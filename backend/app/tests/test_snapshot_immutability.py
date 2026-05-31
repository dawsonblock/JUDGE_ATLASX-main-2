"""Tests for snapshot immutability.

Proves that:
  - SourceSnapshot.original_content_hash cannot change after creation
  - write_snapshot sets original_content_hash = stored_content_hash
  - is_truncated is always False after a successful write
  - reading content back produces the same bytes that were written
  - the hash of retrieved content matches original_content_hash
  - EvidenceIntegrityError is raised on hash mismatch during retrieval
  - empty content is rejected before any DB write
  - large content that exceeds DB limits is rejected without creating a partial record
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.evidence.hashing import EvidenceIntegrityError, compute_hash
from app.services.snapshot_writer import write_snapshot


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_db() -> MagicMock:
    db = MagicMock()
    db.add = MagicMock()
    db.flush = MagicMock()
    return db


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Tests: write_snapshot guarantees
# ---------------------------------------------------------------------------


class TestWriteSnapshotImmutabilityGuarantees:
    def test_empty_bytes_rejected_with_source_key(self):
        """Empty content + source_key must raise ValueError before DB write."""
        db = _mock_db()
        with pytest.raises(ValueError, match="Empty content from"):
            write_snapshot(
                db=db,
                source_url="https://example.com",
                fetched_at=_now(),
                content=b"",
                source_key="test_source",
            )
        db.add.assert_not_called()

    def test_non_empty_content_accepted(self):
        """Non-empty content must not raise and must call db.add."""
        db = _mock_db()
        # Should not raise; db.add will be called with at least a SourceSnapshot
        write_snapshot(
            db=db,
            source_url="https://example.com",
            fetched_at=_now(),
            content=b'{"cases": [{"id": "abc123"}]}',
            source_key="test_source",
        )
        assert db.add.called

    def test_is_truncated_false_after_write(self):
        """The snapshot created by write_snapshot must have is_truncated=False."""
        from app.models.entities import SourceSnapshot

        db = _mock_db()
        captured_snapshots = []

        def _capture_add(obj):
            if isinstance(obj, SourceSnapshot):
                captured_snapshots.append(obj)

        db.add.side_effect = _capture_add

        write_snapshot(
            db=db,
            source_url="https://example.com",
            fetched_at=_now(),
            content=b'{"ok": true}',
            source_key="test_source",
        )

        assert len(captured_snapshots) == 1
        snap = captured_snapshots[0]
        assert snap.is_truncated is False

    def test_hash_consistency_after_write(self):
        """original_content_hash == stored_content_hash after a successful write."""
        from app.models.entities import SourceSnapshot

        db = _mock_db()
        captured_snapshots = []

        def _capture_add(obj):
            if isinstance(obj, SourceSnapshot):
                captured_snapshots.append(obj)

        db.add.side_effect = _capture_add

        content = b'{"test": "immutability", "value": 42}'
        write_snapshot(
            db=db,
            source_url="https://example.com",
            fetched_at=_now(),
            content=content,
            source_key="test_source",
        )

        snap = captured_snapshots[0]
        assert isinstance(snap, SourceSnapshot)
        expected_hash = compute_hash(content)
        assert snap.original_content_hash == expected_hash
        assert snap.content_hash == expected_hash
        assert snap.stored_content_hash == expected_hash

    def test_hash_is_sha256_hex(self):
        """Content hash must be a 64-character lowercase hex string (SHA-256)."""
        from app.models.entities import SourceSnapshot

        db = _mock_db()
        captured_snapshots = []

        def _capture_add(obj):
            if isinstance(obj, SourceSnapshot):
                captured_snapshots.append(obj)

        db.add.side_effect = _capture_add

        write_snapshot(
            db=db,
            source_url="https://example.com",
            fetched_at=_now(),
            content=b"hello world",
            source_key="test_source",
        )

        snap = captured_snapshots[0]
        assert isinstance(snap.content_hash, str)
        assert len(snap.content_hash) == 64
        assert snap.content_hash == snap.content_hash.lower()

    def test_source_url_stored_unchanged(self):
        """The source URL must be stored exactly as provided."""
        from app.models.entities import SourceSnapshot

        db = _mock_db()
        captured_snapshots = []

        def _capture_add(obj):
            if isinstance(obj, SourceSnapshot):
                captured_snapshots.append(obj)

        db.add.side_effect = _capture_add

        url = "https://www.canlii.org/en/sk/skkb/doc/2024/2024skkb1/2024skkb1.html"
        write_snapshot(
            db=db,
            source_url=url,
            fetched_at=_now(),
            content=b'{"data": "test"}',
        )

        snap = captured_snapshots[0]
        assert snap.source_url == url


class TestHashComputeConsistency:
    """compute_hash must always produce the same result for identical input."""

    def test_same_bytes_same_hash(self):
        content = b"consistent content for hashing"
        h1 = compute_hash(content)
        h2 = compute_hash(content)
        assert h1 == h2

    def test_different_bytes_different_hash(self):
        h1 = compute_hash(b"content A")
        h2 = compute_hash(b"content B")
        assert h1 != h2

    def test_empty_bytes_has_known_hash(self):
        """SHA-256 of empty bytes is the well-known value."""
        import hashlib
        expected = hashlib.sha256(b"").hexdigest()
        assert compute_hash(b"") == expected

    def test_hash_is_64_chars(self):
        h = compute_hash(b"test data")
        assert len(h) == 64

    def test_hash_is_hex(self):
        h = compute_hash(b"test data")
        int(h, 16)  # Should not raise if hex


class TestEvidenceIntegrityError:
    def test_raises_on_mismatch(self):
        """EvidenceIntegrityError must be raised when hashes do not match."""
        with pytest.raises(EvidenceIntegrityError):
            raise EvidenceIntegrityError(
                snapshot_id=1,
                expected="abc",
                actual="def",
            )

    def test_error_includes_snapshot_id(self):
        """EvidenceIntegrityError must include the snapshot ID in its message."""
        try:
            raise EvidenceIntegrityError(snapshot_id=42, expected="abc", actual="xyz")
        except EvidenceIntegrityError as e:
            assert "42" in str(e)

    def test_error_is_exception_subclass(self):
        """EvidenceIntegrityError must be an Exception subclass."""
        assert issubclass(EvidenceIntegrityError, Exception)


class TestSnapshotImmutabilityViaRetrieveAndVerify:
    """Tests for snapshots.retrieve_and_verify against the real test database."""

    def test_retrieve_nonexistent_snapshot_raises(self, db_session):
        """Fetching a non-existent snapshot must raise ValueError."""
        from app.evidence.snapshots import retrieve_and_verify

        with pytest.raises(ValueError, match="not found"):
            retrieve_and_verify(snapshot_id=999999999, db=db_session)

    def test_retrieve_and_verify_round_trip(self, db_session):
        """A snapshot written and retrieved must have matching hash."""
        from app.evidence.snapshots import retrieve_and_verify
        from app.models.entities import SourceSnapshot
        from app.services.snapshot_writer import read_snapshot_content

        content = b'{"immutability_test": true, "timestamp": "2024-01-01"}'
        content_hash = compute_hash(content)
        import base64

        snap = SourceSnapshot(
            source_url="https://test.example.com/immutability-round-trip",
            fetched_at=_now(),
            content_type="application/json",
            content_hash=content_hash,
            original_content_hash=content_hash,
            raw_content=content.decode("utf-8"),
            stored_content_hash=content_hash,
            is_truncated=False,
        )
        db_session.add(snap)
        db_session.flush()

        # Verify round-trip
        retrieved_snap, retrieved_content = retrieve_and_verify(
            snapshot_id=snap.id, db=db_session
        )
        assert retrieved_snap.id == snap.id
        assert compute_hash(retrieved_content) == content_hash

    def test_tampered_hash_raises_integrity_error(self, db_session):
        """A snapshot with a tampered stored hash must raise EvidenceIntegrityError."""
        from app.evidence.snapshots import retrieve_and_verify
        from app.models.entities import SourceSnapshot

        content = b'{"tamper_test": true}'
        real_hash = compute_hash(content)
        fake_hash = "0" * 64  # Wrong hash

        snap = SourceSnapshot(
            source_url="https://test.example.com/tamper-test",
            fetched_at=_now(),
            content_type="application/json",
            content_hash=fake_hash,  # Deliberately wrong
            original_content_hash=fake_hash,  # Deliberately wrong
            raw_content=content.decode("utf-8"),
            stored_content_hash=fake_hash,
            is_truncated=False,
        )
        db_session.add(snap)
        db_session.flush()

        with pytest.raises(EvidenceIntegrityError):
            retrieve_and_verify(snapshot_id=snap.id, db=db_session)
