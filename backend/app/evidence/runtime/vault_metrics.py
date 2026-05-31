"""Vault metrics — counters for the evidence vault runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class VaultStat(str, Enum):
    """Named statistics tracked by the vault runtime."""

    SNAPSHOTS_STORED = "snapshots_stored"
    SNAPSHOTS_VERIFIED = "snapshots_verified"
    SNAPSHOTS_EXPIRED = "snapshots_expired"
    SNAPSHOTS_PURGED = "snapshots_purged"
    INTEGRITY_CHECKS = "integrity_checks"
    INTEGRITY_FAILURES = "integrity_failures"
    ADDRESSES_COMPUTED = "addresses_computed"
    RETENTION_EXPIRATIONS = "retention_expirations"
    RETENTION_PURGES = "retention_purges"


class VaultMetrics:
    """Simple counter registry for :class:`VaultStat` values.

    All counters start at 0.  Thread-safety is the caller's responsibility.
    """

    def __init__(self) -> None:
        self._counters: Dict[VaultStat, int] = {s: 0 for s in VaultStat}

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def increment(self, stat: VaultStat, n: int = 1) -> None:
        """Add *n* to *stat*."""
        if n < 0:
            raise ValueError(f"Increment must be non-negative, got {n}")
        self._counters[stat] += n

    def reset(self, stat: Optional[VaultStat] = None) -> None:
        """Reset *stat* to 0, or all stats when *stat* is None."""
        if stat is None:
            for key in self._counters:
                self._counters[key] = 0
        else:
            self._counters[stat] = 0

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(self, stat: VaultStat) -> int:
        return self._counters[stat]

    def snapshot(self) -> Dict[str, int]:
        """Return an immutable copy of all counters keyed by stat value."""
        return {s.value: v for s, v in self._counters.items()}

    @property
    def total_events(self) -> int:
        return sum(self._counters.values())

    def top_n(self, n: int) -> List[Tuple[str, int]]:
        """Return the *n* highest-count stats as ``(name, count)`` pairs."""
        ranked = sorted(self._counters.items(), key=lambda kv: kv[1], reverse=True)
        return [(s.value, v) for s, v in ranked[:n]]

    # ------------------------------------------------------------------
    # Merging
    # ------------------------------------------------------------------

    def merge(self, other: "VaultMetrics") -> None:
        """Add all counters from *other* into this instance in-place."""
        for stat, value in other._counters.items():
            self._counters[stat] += value
