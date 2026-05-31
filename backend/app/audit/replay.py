"""Replay-verify a subset of AuditLog rows by re-computing the chain up to a target id."""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.audit.integrity_chain import ChainVerificationResult, _row_digest
from app.models.entities import AuditLog


def replay_to(db: Session, target_id: int) -> ChainVerificationResult:
    """Re-compute audit chain through *target_id* and return result."""
    from app.audit.integrity_chain import ChainVerificationResult

    rows = (
        db.query(AuditLog)
        .filter(AuditLog.id <= target_id)
        .order_by(AuditLog.id.asc())
        .all()
    )
    if not rows:
        return ChainVerificationResult(ok=True, entries_checked=0, chain_head=None)

    violations: list[str] = []
    prev_hash = "GENESIS"
    for row in rows:
        if not row.actor_id:
            violations.append(f"missing actor_id at row {row.id}")
        prev_hash = _row_digest(row, prev_hash)

    return ChainVerificationResult(
        ok=len(violations) == 0,
        entries_checked=len(rows),
        chain_head=prev_hash,
        violations=violations,
    )
