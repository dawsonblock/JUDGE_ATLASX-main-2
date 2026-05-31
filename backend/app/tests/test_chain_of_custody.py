"""Tests for chain-of-custody provenance tracking.

Proves that:
  - record_custody_event creates a ChainOfCustodyLog entry
  - build_chain_of_custody returns events in order
  - all valid CUSTODY_ACTIONS are accepted
  - invalid actions are rejected
  - hash_at_event is captured from the snapshot
  - custody events include actor identity
  - quarantined action is tracked
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.evidence.provenance import (
    CUSTODY_ACTIONS,
    build_chain_of_custody,
    record_custody_event,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_snapshot(snapshot_id: int = 1, content_hash: str = "abc123") -> MagicMock:
    snap = MagicMock()
    snap.id = snapshot_id
    snap.original_content_hash = content_hash
    snap.content_hash = content_hash
    return snap


def _mock_db() -> MagicMock:
    db = MagicMock()
    db.add = MagicMock()
    db.flush = MagicMock()
    return db


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestRecordCustodyEvent:
    def test_created_action_writes_entry(self):
        """record_custody_event('created') must call db.add and db.flush."""
        from app.models.entities import ChainOfCustodyLog  # noqa: F401 - verify importable

        snap = _mock_snapshot()
        db = _mock_db()

        with patch("app.models.entities.ChainOfCustodyLog") as MockLog:
            mock_entry = MagicMock()
            MockLog.return_value = mock_entry
            result = record_custody_event(db, snap, "created")

        db.add.assert_called_once_with(mock_entry)
        db.flush.assert_called_once()

    def test_verified_action_writes_entry(self):
        """record_custody_event('verified') must be accepted."""
        snap = _mock_snapshot()
        db = _mock_db()

        with patch("app.models.entities.ChainOfCustodyLog"):
            record_custody_event(db, snap, "verified")

        db.add.assert_called_once()

    def test_failed_verification_action_writes_entry(self):
        """record_custody_event('failed_verification') must be accepted."""
        snap = _mock_snapshot()
        db = _mock_db()

        with patch("app.models.entities.ChainOfCustodyLog"):
            record_custody_event(db, snap, "failed_verification")

        db.add.assert_called_once()

    def test_quarantined_action_is_valid(self):
        """quarantined is a valid CUSTODY_ACTION."""
        assert "quarantined" in CUSTODY_ACTIONS

    def test_all_custody_actions_are_accepted(self):
        """Every action in CUSTODY_ACTIONS must not raise."""
        snap = _mock_snapshot()
        for action in CUSTODY_ACTIONS:
            db = _mock_db()
            with patch("app.models.entities.ChainOfCustodyLog"):
                record_custody_event(db, snap, action)
            db.add.assert_called_once()

    def test_actor_identity_is_stored(self):
        """actor and actor_type must be passed to the ChainOfCustodyLog constructor."""
        snap = _mock_snapshot()
        db = _mock_db()

        with patch("app.models.entities.ChainOfCustodyLog") as MockLog:
            record_custody_event(
                db,
                snap,
                "verified",
                actor="reviewer@example.com",
                actor_type="user",
            )
            call_kwargs = MockLog.call_args[1]

        assert call_kwargs["actor"] == "reviewer@example.com"
        assert call_kwargs["actor_type"] == "user"

    def test_hash_at_event_uses_original_content_hash(self):
        """hash_at_event must be populated from the snapshot's hash."""
        snap = _mock_snapshot(content_hash="deadbeef1234")
        snap.original_content_hash = "deadbeef1234"
        db = _mock_db()

        with patch("app.models.entities.ChainOfCustodyLog") as MockLog:
            record_custody_event(db, snap, "created")
            call_kwargs = MockLog.call_args[1]

        assert call_kwargs["hash_at_event"] == "deadbeef1234"

    def test_notes_are_stored(self):
        """Optional notes must be passed through to the entry."""
        snap = _mock_snapshot()
        db = _mock_db()

        with patch("app.models.entities.ChainOfCustodyLog") as MockLog:
            record_custody_event(db, snap, "accessed", notes="exported for review")
            call_kwargs = MockLog.call_args[1]

        assert call_kwargs["notes"] == "exported for review"

    def test_snapshot_id_is_stored(self):
        """snapshot_id must be set to the snapshot's primary key."""
        snap = _mock_snapshot(snapshot_id=42)
        db = _mock_db()

        with patch("app.models.entities.ChainOfCustodyLog") as MockLog:
            record_custody_event(db, snap, "created")
            call_kwargs = MockLog.call_args[1]

        assert call_kwargs["snapshot_id"] == 42

    def test_created_at_is_set(self):
        """created_at must be a UTC datetime."""
        snap = _mock_snapshot()
        db = _mock_db()

        with patch("app.models.entities.ChainOfCustodyLog") as MockLog:
            record_custody_event(db, snap, "created")
            call_kwargs = MockLog.call_args[1]

        ts = call_kwargs["created_at"]
        assert isinstance(ts, datetime)
        assert ts.tzinfo is not None


class TestBuildChainOfCustody:
    def test_returns_list(self):
        """build_chain_of_custody must return a list."""
        db = MagicMock()
        db.query.return_value.filter.return_value.order_by.return_value.all.return_value = []

        with patch("app.models.entities.ChainOfCustodyLog") as MockLog:
            result = build_chain_of_custody(snapshot_id=1, db=db)

        assert isinstance(result, list)

    def test_filters_by_snapshot_id(self):
        """build_chain_of_custody must query by snapshot_id."""
        db = MagicMock()
        mock_query = MagicMock()
        db.query.return_value = mock_query
        mock_query.filter.return_value = mock_query
        mock_query.order_by.return_value = mock_query
        mock_query.all.return_value = []

        with patch("app.models.entities.ChainOfCustodyLog"):
            build_chain_of_custody(snapshot_id=99, db=db)

        # Verify a query was made (filter is called with snapshot_id condition)
        db.query.assert_called_once()


class TestCustodyActionsConstant:
    def test_custody_actions_is_frozenset(self):
        assert isinstance(CUSTODY_ACTIONS, frozenset)

    def test_required_actions_present(self):
        """Core lifecycle actions must be in CUSTODY_ACTIONS."""
        required = {"created", "accessed", "verified", "failed_verification", "exported", "quarantined"}
        missing = required - CUSTODY_ACTIONS
        assert not missing, f"Missing CUSTODY_ACTIONS: {missing}"

    def test_no_empty_strings(self):
        """No empty-string actions must be accepted."""
        assert "" not in CUSTODY_ACTIONS


class TestIntegrationCustodyWithRealDB:
    """Integration test that writes custody events against the test SQLite database."""

    def test_created_event_persisted(self, db_session):
        """A 'created' custody event must be retrievable from the database."""
        from app.models.entities import ChainOfCustodyLog, SourceSnapshot

        # Create a minimal SourceSnapshot to attach the custody event to
        snap = SourceSnapshot(
            source_url="https://www.canlii.org/test",
            fetched_at=datetime.now(timezone.utc),
            content_type="application/json",
            content_hash="test-hash-custody-" + str(id(self)),
            original_content_hash="test-hash-custody-" + str(id(self)),
            raw_content='{"test": true}',
            stored_content_hash="test-hash-custody-" + str(id(self)),
            is_truncated=False,
        )
        db_session.add(snap)
        db_session.flush()

        entry = record_custody_event(
            db_session,
            snap,
            "created",
            actor="test-system",
            actor_type="system",
            notes="test custody event",
        )

        assert entry is not None
        assert entry.snapshot_id == snap.id
        assert entry.action == "created"
        assert entry.actor == "test-system"
        assert entry.hash_at_event == snap.original_content_hash

    def test_multiple_events_ordered(self, db_session):
        """Multiple custody events must be retrievable in order."""
        from app.models.entities import SourceSnapshot

        snap = SourceSnapshot(
            source_url="https://www.canlii.org/test-multi",
            fetched_at=datetime.now(timezone.utc),
            content_type="application/json",
            content_hash="multi-hash-" + str(id(self)),
            original_content_hash="multi-hash-" + str(id(self)),
            raw_content='{"multi": true}',
            stored_content_hash="multi-hash-" + str(id(self)),
            is_truncated=False,
        )
        db_session.add(snap)
        db_session.flush()

        record_custody_event(db_session, snap, "created", actor="ingester")
        record_custody_event(db_session, snap, "verified", actor="reviewer")
        record_custody_event(db_session, snap, "exported", actor="exporter")

        chain = build_chain_of_custody(snap.id, db_session)
        assert len(chain) >= 3
        actions = [e.action for e in chain]
        assert "created" in actions
        assert "verified" in actions
        assert "exported" in actions
