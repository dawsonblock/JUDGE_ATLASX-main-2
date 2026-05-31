"""Tests for services/evidence_integrity.py.

Covers:
- verify_snapshot_integrity: pass, hash mismatch, missing snapshot, no content
- verify_all_recent_snapshots: delegates correctly
- assert_snapshot_append_only_change: blocks immutable fields, allows mutable
- record_custody_event: raises on missing snapshot, delegates to provenance
- _block_immutable_update SQLAlchemy event: raises on change, passes on same value
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, call, patch

import pytest
from sqlalchemy.orm.attributes import set_committed_value

from app.evidence.hashing import compute_hash
from app.models.entities import SourceSnapshot
from app.services.evidence_integrity import (
    IMMUTABLE_SNAPSHOT_FIELDS,
    ImmutabilityViolation,
    IntegrityResult,
    _block_immutable_update,
    assert_snapshot_append_only_change,
    record_custody_event,
    verify_all_recent_snapshots,
    verify_snapshot_integrity,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NOW = datetime(2024, 1, 1, tzinfo=timezone.utc)
_CONTENT = b"canonical source content"
_HASH = compute_hash(_CONTENT)


def _mock_db(snapshot: SourceSnapshot | None = None) -> MagicMock:
    """Return a MagicMock db session whose ``get`` returns *snapshot*."""
    db = MagicMock()
    db.get.return_value = snapshot
    return db


def _make_snapshot(
    snap_id: int = 1,
    content: bytes = _CONTENT,
    raw_content: str | None = None,
    storage_backend: str = "db",
) -> SourceSnapshot:
    """Construct a minimal SourceSnapshot without a real DB session."""
    snap = SourceSnapshot(
        id=snap_id,
        source_url="https://example.com/evidence.html",
        fetched_at=_NOW,
        content_hash=compute_hash(content),
        raw_content=raw_content if raw_content is not None else content.decode(),
        storage_backend=storage_backend,
    )
    snap.id = snap_id
    return snap


# ---------------------------------------------------------------------------
# verify_snapshot_integrity
# ---------------------------------------------------------------------------


class TestVerifySnapshotIntegrity:
    def test_pass_when_hash_matches(self):
        """DB-backed snapshot: re-hashed content matches stored hash → ok=True."""
        snap = _make_snapshot(snap_id=10, content=_CONTENT)
        db = _mock_db(snap)

        with patch(
            "app.services.evidence_integrity.read_snapshot_content",
            return_value=_CONTENT,
        ):
            result = verify_snapshot_integrity(10, db)

        assert result.ok is True
        assert result.snapshot_id == 10
        assert result.expected_hash == _HASH
        assert result.actual_hash == _HASH
        assert result.error_message is None

    def test_fail_when_hash_mismatch(self):
        """Tampered content produces a different hash → ok=False."""
        snap = _make_snapshot(snap_id=11, content=_CONTENT)
        db = _mock_db(snap)
        tampered = b"TAMPERED " + _CONTENT

        with patch(
            "app.services.evidence_integrity.read_snapshot_content",
            return_value=tampered,
        ):
            result = verify_snapshot_integrity(11, db)

        assert result.ok is False
        assert result.snapshot_id == 11
        assert result.expected_hash == _HASH
        assert result.actual_hash == compute_hash(tampered)
        assert "Hash mismatch" in (result.error_message or "")

    def test_missing_snapshot_returns_error_result(self):
        """Querying a non-existent ID returns ok=False with an error message."""
        db = _mock_db(None)

        result = verify_snapshot_integrity(999, db)

        assert result.ok is False
        assert result.snapshot_id == 999
        assert "not found" in (result.error_message or "")

    def test_no_content_returns_error_result(self):
        """read_snapshot_content returns None → ok=False with helpful message."""
        snap = _make_snapshot(snap_id=12, content=_CONTENT)
        db = _mock_db(snap)

        with patch(
            "app.services.evidence_integrity.read_snapshot_content",
            return_value=None,
        ):
            result = verify_snapshot_integrity(12, db)

        assert result.ok is False
        assert "No content available" in (result.error_message or "")

    def test_oserror_from_store_returns_error_result(self):
        """OSError from read_snapshot_content propagates as error, not exception."""
        snap = _make_snapshot(snap_id=13, content=_CONTENT)
        db = _mock_db(snap)

        with patch(
            "app.services.evidence_integrity.read_snapshot_content",
            side_effect=OSError("file not found"),
        ):
            result = verify_snapshot_integrity(13, db)

        assert result.ok is False
        assert "file not found" in (result.error_message or "")


# ---------------------------------------------------------------------------
# verify_all_recent_snapshots
# ---------------------------------------------------------------------------


class TestVerifyAllRecentSnapshots:
    def test_queries_recent_snapshots_and_delegates(self):
        """Should call verify_snapshot_integrity for each snapshot returned."""
        snap_a = _make_snapshot(snap_id=1)
        snap_b = _make_snapshot(snap_id=2)

        db = MagicMock()
        # Simulate db.query(...).order_by(...).limit(...).all()
        db.query.return_value.order_by.return_value.limit.return_value.all.return_value = [
            snap_a,
            snap_b,
        ]
        # db.get called inside verify_snapshot_integrity for each snap
        db.get.side_effect = [snap_a, snap_b]

        with patch(
            "app.services.evidence_integrity.read_snapshot_content",
            return_value=_CONTENT,
        ):
            results = verify_all_recent_snapshots(db, limit=10)

        assert len(results) == 2
        assert all(r.ok for r in results)

    def test_respects_limit_parameter(self):
        """The limit is forwarded to the query."""
        db = MagicMock()
        db.query.return_value.order_by.return_value.limit.return_value.all.return_value = []

        verify_all_recent_snapshots(db, limit=5)

        db.query.return_value.order_by.return_value.limit.assert_called_once_with(5)


# ---------------------------------------------------------------------------
# assert_snapshot_append_only_change
# ---------------------------------------------------------------------------


class TestAssertSnapshotAppendOnlyChange:
    def _ns(self, **kwargs) -> SimpleNamespace:
        defaults = {
            "id": 1,
            "content_hash": "h1",
            "source_url": "https://example.com",
            "fetched_at": _NOW,
            "raw_content": "content",
            "stored_content_hash": "sh1",
            "original_content_hash": "oh1",
            "error_message": None,
        }
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def test_raises_on_content_hash_change(self):
        old = self._ns(content_hash="old_hash")
        new = self._ns(content_hash="new_hash")
        with pytest.raises(ImmutabilityViolation, match="content_hash"):
            assert_snapshot_append_only_change(old, new)

    def test_raises_on_source_url_change(self):
        old = self._ns(source_url="https://old.example.com")
        new = self._ns(source_url="https://new.example.com")
        with pytest.raises(ImmutabilityViolation, match="source_url"):
            assert_snapshot_append_only_change(old, new)

    def test_raises_on_fetched_at_change(self):
        old = self._ns(fetched_at=datetime(2024, 1, 1, tzinfo=timezone.utc))
        new = self._ns(fetched_at=datetime(2024, 6, 1, tzinfo=timezone.utc))
        with pytest.raises(ImmutabilityViolation, match="fetched_at"):
            assert_snapshot_append_only_change(old, new)

    def test_allows_mutable_field_change(self):
        """Changing error_message (mutable) must not raise."""
        old = self._ns(error_message=None)
        new = self._ns(error_message="retrieval failed")
        # No exception expected
        assert_snapshot_append_only_change(old, new)

    def test_snapshot_id_included_in_violation_message(self):
        old = self._ns(id=42, content_hash="h1")
        new = self._ns(id=42, content_hash="h2")
        with pytest.raises(ImmutabilityViolation) as exc_info:
            assert_snapshot_append_only_change(old, new)
        assert "42" in str(exc_info.value)


# ---------------------------------------------------------------------------
# record_custody_event
# ---------------------------------------------------------------------------


class TestRecordCustodyEvent:
    def test_raises_when_snapshot_not_found(self):
        db = _mock_db(None)
        with pytest.raises(ValueError, match="not found"):
            record_custody_event(snapshot_id=404, actor="system", action="verified", db=db)

    def test_delegates_to_provenance(self):
        snap = _make_snapshot(snap_id=5)
        db = _mock_db(snap)

        with patch("app.evidence.provenance.record_custody_event") as mock_record:
            record_custody_event(
                snapshot_id=5, actor="admin", action="verified", db=db
            )

        mock_record.assert_called_once_with(db, snap, "verified", actor="admin")


# ---------------------------------------------------------------------------
# _block_immutable_update SQLAlchemy event handler
# ---------------------------------------------------------------------------


class TestBlockImmutableUpdate:
    def test_raises_when_immutable_field_changed(self):
        """Event handler raises ImmutabilityViolation when content_hash is changed."""
        snap = SourceSnapshot()
        snap.id = 99
        # Set the "committed" (DB) value so get_history sees a change
        set_committed_value(snap, "content_hash", "old_hash")
        snap.content_hash = "new_hash"

        with pytest.raises(ImmutabilityViolation, match="content_hash"):
            _block_immutable_update(None, None, snap)

    def test_no_raise_when_field_unchanged(self):
        """Re-assigning the same value does not raise."""
        snap = SourceSnapshot()
        snap.id = 100
        set_committed_value(snap, "content_hash", "same_hash")
        snap.content_hash = "same_hash"

        # Should not raise
        _block_immutable_update(None, None, snap)

    def test_no_raise_when_no_history(self):
        """Brand-new instance with no prior DB value does not raise."""
        snap = SourceSnapshot()
        snap.id = 101
        snap.content_hash = "first_set"

        # No raise — no deleted history, this is an initial assignment
        _block_immutable_update(None, None, snap)
