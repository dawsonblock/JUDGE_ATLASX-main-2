"""Proves verify_chain() detects a broken previous_entry_hash link.

When a row's previous_entry_hash does not match the entry_hash of the
preceding row, the chain is broken and verify_chain() must report a
violation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.audit.chain_digest import GENESIS_HASH, compute_payload_hash, row_digest
from app.audit.integrity_chain import verify_chain
from app.models.entities import AuditLog


def _make_row(
    row_id: int,
    action: str = "test.action",
    actor_id: str = "admin-1",
    prev_hash: str = GENESIS_HASH,
) -> AuditLog:
    payload: dict = {}
    row = AuditLog(
        id=row_id,
        action=action,
        entity_type="test",
        entity_id="1",
        actor_id=actor_id,
        actor_type="admin",
        actor_role="admin",
        actor_auth_method="jwt",
        payload=payload,
        created_at=datetime(2026, 1, 1, 0, 0, row_id, tzinfo=timezone.utc),
        previous_entry_hash=prev_hash,
        chain_version=2,
        payload_hash=compute_payload_hash(payload),
    )
    row.entry_hash = row_digest(row, prev_hash)
    return row


def _mock_db(rows: list[AuditLog]) -> MagicMock:
    db = MagicMock()
    query_mock = MagicMock()
    order_mock = MagicMock()
    order_mock.all.return_value = rows
    query_mock.order_by.return_value = order_mock
    db.query.return_value = query_mock
    return db


def _build_chain(*actions: str) -> list[AuditLog]:
    rows: list[AuditLog] = []
    prev = GENESIS_HASH
    for i, action in enumerate(actions, start=1):
        row = _make_row(i, action=action, prev_hash=prev)
        prev = row.entry_hash  # type: ignore[assignment]
        rows.append(row)
    return rows


class TestBrokenPreviousHash:
    def test_clean_chain_passes(self) -> None:
        rows = _build_chain("a.created", "b.updated", "c.deleted")
        db = _mock_db(rows)
        result = verify_chain(db)
        assert result.ok

    def test_broken_link_single_row_detected(self) -> None:
        """Mutate row 2's previous_entry_hash so it no longer links to row 1."""
        rows = _build_chain("a.created", "b.updated", "c.deleted")
        rows[1].previous_entry_hash = "000000deadbeef"  # break the link
        db = _mock_db(rows)
        result = verify_chain(db)
        assert not result.ok
        assert len(result.violations) >= 1

    def test_broken_link_last_row_detected(self) -> None:
        """Break the link at the last row."""
        rows = _build_chain("a.created", "b.updated", "c.deleted")
        rows[-1].previous_entry_hash = "ffffffffffffffff"
        db = _mock_db(rows)
        result = verify_chain(db)
        assert not result.ok

    def test_first_row_wrong_genesis_detected(self) -> None:
        """First row must link to GENESIS_HASH; any other value is a violation."""
        rows = _build_chain("a.created")
        rows[0].previous_entry_hash = "not-genesis"
        db = _mock_db(rows)
        result = verify_chain(db)
        assert not result.ok

    def test_all_broken_links_reported(self) -> None:
        """All broken links in a chain must each appear as violations."""
        rows = _build_chain("a.created", "b.updated", "c.deleted")
        rows[1].previous_entry_hash = "bad-hash-1"
        rows[2].previous_entry_hash = "bad-hash-2"
        db = _mock_db(rows)
        result = verify_chain(db)
        assert not result.ok
        assert len(result.violations) >= 2
