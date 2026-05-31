"""Tests for snapshot empty-bytes guard (Phase 4 hardening).

Verifies that:
- write_snapshot raises ValueError for empty bytes when source_key is set
- write_snapshot accepts a single-byte payload without raising
- _create_snapshot quarantines the IngestionRun on empty raw_content
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.services.snapshot_writer import write_snapshot


def _mock_db() -> MagicMock:
    db = MagicMock()
    db.add = MagicMock()
    return db


# ---------------------------------------------------------------------------
# write_snapshot unit tests
# ---------------------------------------------------------------------------


def test_write_snapshot_raises_on_empty_bytes():
    """Empty bytes + source_key → ValueError before any DB write."""
    db = _mock_db()
    with pytest.raises(ValueError, match="Empty content from 'test_source'"):
        write_snapshot(
            db=db,
            source_url="https://example.com",
            fetched_at=datetime.now(timezone.utc),
            content=b"",
            source_key="test_source",
        )
    db.add.assert_not_called()


def test_write_snapshot_accepts_single_byte():
    """A non-empty payload must not trigger the empty-bytes guard."""
    db = _mock_db()
    # Should not raise; db.add will be called to create the snapshot
    write_snapshot(
        db=db,
        source_url="https://example.com",
        fetched_at=datetime.now(timezone.utc),
        content=b"\x00",
        source_key="test_source",
    )
    assert db.add.call_count >= 1


def test_write_snapshot_empty_bytes_no_source_key_does_not_raise():
    """Empty bytes without a source_key must NOT raise (anonymous callers OK)."""
    db = _mock_db()
    # source_key=None means no named source; guard should not fire
    write_snapshot(
        db=db,
        source_url="https://example.com",
        fetched_at=datetime.now(timezone.utc),
        content=b"",
        source_key=None,
    )
    assert db.add.call_count >= 1


# ---------------------------------------------------------------------------
# _create_snapshot quarantine test
# ---------------------------------------------------------------------------


def test_create_snapshot_quarantines_run_on_empty_raw_content():
    """_create_snapshot with raw_content=None quarantines the run and re-raises."""
    from app.ingestion.source_runner import _create_snapshot

    db = _mock_db()
    source = SimpleNamespace(
        source_key="test_source",
        base_url="https://example.com",
    )
    run_record = SimpleNamespace(
        id=42,
        status="running",
        quarantine_reason=None,
    )

    with patch(
        "app.services.snapshot_writer.write_snapshot",
        side_effect=ValueError("Empty content from 'test_source'"),
    ):
        with pytest.raises(ValueError, match="Empty content"):
            _create_snapshot(db, source, run_record, raw_content=None)

    assert run_record.status == "quarantined"
    assert run_record.quarantine_reason == "no_raw_content"
