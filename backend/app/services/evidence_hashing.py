"""Backward-compatible shim: re-exports from app.evidence.hashing.

Any code that imported directly from ``app.services.evidence_hashing``
(before the evidence vault module was created) will continue to work.
"""

from app.evidence.hashing import (  # noqa: F401
    EvidenceIntegrityError,
    compute_hash,
    verify_hash,
)

__all__ = ["EvidenceIntegrityError", "compute_hash", "verify_hash"]
