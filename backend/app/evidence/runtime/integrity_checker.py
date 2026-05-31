"""Integrity checker — verifies evidence blobs against expected hashes."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class IntegrityResult:
    """Result of a single integrity check.

    Attributes
    ----------
    ok:
        True when *actual_hash* == *expected_hash*.
    expected_hash:
        The hash the caller believes the content should have.
    actual_hash:
        The hash computed from the provided content bytes.
    snapshot_id:
        Optional identifier to correlate the result with a DB record.
    """

    ok: bool
    expected_hash: str
    actual_hash: str
    snapshot_id: Optional[int] = None

    @property
    def is_tampered(self) -> bool:
        """True when the check failed (content does not match expected hash)."""
        return not self.ok

    @property
    def mismatch_prefix(self) -> str:
        """Return the first 16 chars of both hashes for logging."""
        return f"exp={self.expected_hash[:16]} got={self.actual_hash[:16]}"

    def __str__(self) -> str:
        status = "OK" if self.ok else "FAIL"
        sid = f" sid={self.snapshot_id}" if self.snapshot_id is not None else ""
        return f"IntegrityResult({status}{sid} {self.mismatch_prefix})"


class IntegrityChecker:
    """Checks evidence content against expected SHA-256 hashes."""

    # ------------------------------------------------------------------
    # Single-item checks
    # ------------------------------------------------------------------

    def check(
        self,
        content: bytes,
        expected_hash: str,
        snapshot_id: Optional[int] = None,
    ) -> IntegrityResult:
        """Hash *content* and compare to *expected_hash*.

        Parameters
        ----------
        content:
            Raw bytes of the evidence blob.
        expected_hash:
            SHA-256 hex digest the content should produce.
        snapshot_id:
            Optional snapshot identifier for correlation.
        """
        actual = hashlib.sha256(content).hexdigest()
        return IntegrityResult(
            ok=(actual == expected_hash),
            expected_hash=expected_hash,
            actual_hash=actual,
            snapshot_id=snapshot_id,
        )

    def check_hex(
        self,
        actual_hash: str,
        expected_hash: str,
        snapshot_id: Optional[int] = None,
    ) -> IntegrityResult:
        """Compare two pre-computed hex digests (no re-hashing)."""
        return IntegrityResult(
            ok=(actual_hash == expected_hash),
            expected_hash=expected_hash,
            actual_hash=actual_hash,
            snapshot_id=snapshot_id,
        )

    # ------------------------------------------------------------------
    # Batch checks
    # ------------------------------------------------------------------

    def check_batch(
        self,
        items: Sequence[Tuple[bytes, str]],
    ) -> List[IntegrityResult]:
        """Check multiple (content, expected_hash) pairs in sequence.

        Parameters
        ----------
        items:
            Iterable of ``(content_bytes, expected_hash)`` tuples.

        Returns
        -------
        list[IntegrityResult]
            Results in the same order as *items*.
        """
        return [self.check(content, expected) for content, expected in items]

    def check_batch_with_ids(
        self,
        items: Sequence[Tuple[int, bytes, str]],
    ) -> List[IntegrityResult]:
        """Like :meth:`check_batch` but each entry starts with a *snapshot_id*.

        Parameters
        ----------
        items:
            Iterable of ``(snapshot_id, content_bytes, expected_hash)`` tuples.
        """
        return [
            self.check(content, expected, snapshot_id=sid)
            for sid, content, expected in items
        ]

    # ------------------------------------------------------------------
    # Aggregate helpers
    # ------------------------------------------------------------------

    @staticmethod
    def all_ok(results: Sequence[IntegrityResult]) -> bool:
        """True when every result in *results* passed."""
        return all(r.ok for r in results)

    @staticmethod
    def failures(results: Sequence[IntegrityResult]) -> List[IntegrityResult]:
        """Return only the failed results."""
        return [r for r in results if not r.ok]

    @staticmethod
    def failure_count(results: Sequence[IntegrityResult]) -> int:
        return sum(1 for r in results if not r.ok)
