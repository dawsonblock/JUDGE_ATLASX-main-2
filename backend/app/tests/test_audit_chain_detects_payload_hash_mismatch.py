"""Proves verify_chain() detects a payload_hash mismatch.

When a row's stored payload_hash does not match the hash recomputed from
the stored payload, the chain verifier must report a violation.
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
    payload: dict | None = None,
    prev_hash: str = GENESIS_HASH,
) -> AuditLog:
    p = payload or {}
    row = AuditLog(
        id=row_id,
        action=action,
        entity_type="test",
        entity_id="1",
        actor_id="admin-1",
        actor_type="admin",
        actor_role="admin",
        actor_auth_method="jwt",
        payload=p,
        created_at=datetime(2026, 1, 1, 0, 0, row_id, tzinfo=timezone.utc),
        previous_entry_hash=prev_hash,
        chain_version=2,
        payload_hash=compute_payload_hash(p),
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


class TestPayloadHashMismatch:
    def test_clean_chain_passes(self) -> None:
        rows = _build_chain("a.created", "b.updated", "c.deleted")
        db = _mock_db(rows)
        result = verify_chain(db)
        assert result.ok

    def test_mutated_payload_hash_detected(self) -> None:
        """Directly overwrite payload_hash with a wrong value."""
        rows = _build_chain("a.created", "b.updated", "c.deleted")
        rows[1].payload_hash = "000000000000000000000000000000000000000000000000000000000000dead"
        db = _mock_db(rows)
        result = verify_chain(db)
        assert not result.ok
        assert len(result.violations) >= 1

    def test_mutated_payload_content_detected(self) -> None:
        """Change the stored payload dict without updating payload_hash."""
        rows = _build_chain("a.created", "b.updated")
        rows[0].payload = {"injected": "value"}  # payload_hash no longer matches
        db = _mock_db(rows)
        result = verify_chain(db)
        assert not result.ok

    def test_all_rows_payload_mismatch_detected(self) -> None:
        """Every row with a bad payload_hash must produce a violation."""
        rows = _build_chain("a.created", "b.updated", "c.deleted")
        for row in rows:
            row.payload_hash = "badhash"
        db = _mock_db(rows)
        result = verify_chain(db)
        assert not result.ok
        assert len(result.violations) >= 3

    def test_last_row_payload_mismatch_detected(self) -> None:
        """Mismatch at the chain tail is still reported."""
        rows = _build_chain("a.created", "b.updated", "c.deleted")
        rows[-1].payload_hash = "ffff"
        db = _mock_db(rows)
        result = verify_chain(db)
        assert not result.ok
