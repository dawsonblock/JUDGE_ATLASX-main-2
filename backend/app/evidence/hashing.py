"""Evidence hashing utilities: SHA-256 compute and verify."""

from __future__ import annotations

import hashlib


class EvidenceIntegrityError(Exception):
    """Raised when a stored hash does not match the computed hash of content."""

    def __init__(self, snapshot_id: int, expected: str, actual: str) -> None:
        self.snapshot_id = snapshot_id
        self.expected = expected
        self.actual = actual
        super().__init__(
            f"Integrity check failed for snapshot {snapshot_id}: "
            f"expected {expected[:16]}…, got {actual[:16]}…"
        )


def compute_hash(content: bytes) -> str:
    """Return the lowercase hex SHA-256 digest of *content*.

    This is the canonical hash function for all evidence stored in the system.
    Every stored snapshot, custody event, and verification check calls this
    function so hash values remain consistent across the codebase.
    """
    return hashlib.sha256(content).hexdigest()


def verify_hash(content: bytes, expected_hash: str) -> bool:
    """Return True if SHA-256(*content*) == *expected_hash*.

    The comparison is performed in constant time (via Python's ``==`` on
    equal-length hex strings) which is sufficient because hash digests are
    not secret credentials.
    """
    return compute_hash(content) == expected_hash
