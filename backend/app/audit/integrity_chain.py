"""Verify the hash-linked integrity of the AuditLog chain."""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.audit.chain_digest import (
    CURRENT_CHAIN_VERSION,
    GENESIS_HASH,
    compute_payload_hash,
    row_digest,
)
from app.models.entities import AuditLog

_VALID_CHAIN_VERSIONS = frozenset({1, 2})


@dataclass
class ChainVerificationResult:
    ok: bool
    entries_checked: int
    chain_head: str | None  # SHA-256 of last row
    violations: list[str] = field(default_factory=list)


def verify_chain(db: Session) -> ChainVerificationResult:
    """Read all AuditLog rows in id-ascending order and check chain integrity.

    Checks:
    - Non-empty audit log (at least 1 entry required)
    - Monotonic id ordering
    - Monotonic timestamp ordering
    - actor_id present
    - actor_role present (chain v2+)
    - actor_auth_method present (chain v2+)
    - action present
    - created_at present
    - chain_version valid (1 or 2)
    - payload_hash matches recomputed payload hash (chain v2 only)
    - previous_entry_hash == expected previous hash
    - entry_hash matches recomputed entry_hash
    """
    rows = db.query(AuditLog).order_by(AuditLog.id.asc()).all()
    
    violations: list[str] = []
    
    # Empty chain is a violation
    if not rows:
        return ChainVerificationResult(ok=False, entries_checked=0, chain_head=None, violations=["empty_audit_log"])

    prev_hash = GENESIS_HASH
    prev_id: int | None = None
    prev_ts = None

    for row in rows:
        # Monotonic ID check
        if prev_id is not None and row.id <= prev_id:
            violations.append(f"non-monotonic id at row {row.id}")

        # Monotonic timestamp check
        if prev_ts is not None and row.created_at is not None:
            if row.created_at < prev_ts:
                violations.append(f"timestamp regression at row {row.id}")

        # Required fields
        if not row.actor_id:
            violations.append(f"missing actor_id at row {row.id}")

        if not row.action:
            violations.append(f"missing action at row {row.id}")

        if row.created_at is None:
            violations.append(f"missing created_at at row {row.id}")

        # Chain version check
        cv = getattr(row, "chain_version", None)
        if cv is not None and cv not in _VALID_CHAIN_VERSIONS:
            violations.append(f"invalid chain_version={cv} at row {row.id}")

        # Chain v2+ specific required fields
        if cv is not None and cv >= 2:
            if not getattr(row, "actor_role", None):
                violations.append(f"missing actor_role in chain v{cv} at row {row.id}")
            if not getattr(row, "actor_auth_method", None):
                violations.append(f"missing actor_auth_method in chain v{cv} at row {row.id}")

        # Payload hash check (chain v2 only — rows with chain_version >= 2)
        if cv is not None and cv >= 2:
            stored_ph = getattr(row, "payload_hash", None)
            if stored_ph is not None:
                recomputed_ph = compute_payload_hash(row.payload)
                if stored_ph != recomputed_ph:
                    violations.append(
                        f"payload_hash mismatch at row {row.id}: "
                        f"stored={stored_ph!r} recomputed={recomputed_ph!r}"
                    )

        # Previous entry hash check
        stored_prev = getattr(row, "previous_entry_hash", None)
        if stored_prev is not None and stored_prev != prev_hash:
            violations.append(
                f"previous_entry_hash mismatch at row {row.id}: "
                f"stored={stored_prev!r} expected={prev_hash!r}"
            )

        # Entry hash check
        recomputed = row_digest(row, prev_hash)
        if row.entry_hash is not None and row.entry_hash != recomputed:
            violations.append(
                f"stored entry_hash mismatch at row {row.id}: "
                f"stored={row.entry_hash!r} recomputed={recomputed!r}"
            )

        prev_hash = recomputed
        prev_id = row.id
        if row.created_at is not None:
            prev_ts = row.created_at

    return ChainVerificationResult(
        ok=len(violations) == 0,
        entries_checked=len(rows),
        chain_head=prev_hash,
        violations=violations,
    )
