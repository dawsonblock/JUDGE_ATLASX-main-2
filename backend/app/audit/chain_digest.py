"""Shared row-digest helper for the AuditLog integrity chain.

Extracted here to avoid circular imports between admin.py (which writes
log entries) and integrity_chain.py (which verifies them).

Chain version history:
  1 — initial (entry_hash + previous_entry_hash only)
  2 — extended: adds payload_hash, before_hash, after_hash,
      actor_role, actor_auth_method, created_at, chain_version
"""
from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.models.entities import AuditLog

GENESIS_HASH = "GENESIS"
CURRENT_CHAIN_VERSION = 2


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def compute_payload_hash(payload: dict[str, Any] | None) -> str:
    """Return SHA-256 hex digest of deterministically serialised payload."""
    canonical = json.dumps(payload or {}, sort_keys=True, default=str)
    return _hash_bytes(canonical.encode())


def row_digest(row: "AuditLog", prev_hash: str) -> str:
    """Return the SHA-256 hex digest for *row* chained to *prev_hash*.

    Includes all chain-v2 fields so the digest is fully self-describing.
    Rows written with chain_version=1 (legacy) still recompute correctly
    because missing Optional fields serialise as None → "null".
    """
    # Stable datetime string — always UTC ISO-8601 with 'Z' suffix
    created_at_str: str | None
    if row.created_at is not None:
        ts = row.created_at
        # Ensure UTC-aware
        if ts.tzinfo is None:
            from datetime import timezone
            ts = ts.replace(tzinfo=timezone.utc)
        created_at_str = ts.strftime("%Y-%m-%dT%H:%M:%S.%f+00:00")
    else:
        created_at_str = None

    canonical = json.dumps(
        {
            "id": row.id,
            "action": row.action,
            "actor_id": row.actor_id,
            "actor_role": row.actor_role,
            "actor_auth_method": getattr(row, "actor_auth_method", None),
            "entity_type": row.entity_type,
            "entity_id": row.entity_id,
            "payload_hash": getattr(row, "payload_hash", None),
            "before_hash": getattr(row, "before_hash", None),
            "after_hash": getattr(row, "after_hash", None),
            "created_at": created_at_str,
            "chain_version": getattr(row, "chain_version", None) or CURRENT_CHAIN_VERSION,
            "prev": prev_hash,
        },
        sort_keys=True,
        default=str,
    )
    return _hash_bytes(canonical.encode())
