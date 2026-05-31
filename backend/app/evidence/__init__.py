"""Evidence vault: hashing, provenance, chain-of-custody, and extraction."""

from app.evidence.hashing import (
    EvidenceIntegrityError,
    compute_hash,
    verify_hash,
)
from app.evidence.provenance import build_chain_of_custody, record_custody_event
from app.evidence.snapshots import retrieve_and_verify

__all__ = [
    "EvidenceIntegrityError",
    "compute_hash",
    "verify_hash",
    "build_chain_of_custody",
    "record_custody_event",
    "retrieve_and_verify",
]
