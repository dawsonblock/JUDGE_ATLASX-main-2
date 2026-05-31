"""Memory subsystem metrics collector.

Deterministic, thread-safe for single-threaded use; no DB or I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List


class MemoryMetricStat(str, Enum):
    """Named counters tracked by :class:`MemoryMetrics`."""

    CLAIMS_ACTIVATED = "claims_activated"
    CLAIMS_INVALIDATED = "claims_invalidated"
    CLAIMS_STALED = "claims_staled"
    CLAIMS_ARCHIVED = "claims_archived"
    REBUILDS_SCHEDULED = "rebuilds_scheduled"
    REBUILDS_COMPLETED = "rebuilds_completed"
    REBUILDS_FAILED = "rebuilds_failed"
    CACHE_HITS = "cache_hits"
    CACHE_MISSES = "cache_misses"
    CACHE_EVICTIONS = "cache_evictions"
    DIFF_RUNS = "diff_runs"
    DIFF_ADDED = "diff_added"
    DIFF_REMOVED = "diff_removed"
    DIFF_MODIFIED = "diff_modified"


@dataclass
class MemoryMetrics:
    """Accumulates counters for the memory runtime subsystem.

    Each counter is keyed by a :class:`MemoryMetricStat`.
    """

    _counters: Dict[str, int] = field(default_factory=dict, repr=False)

    def increment(self, stat: MemoryMetricStat, by: int = 1) -> int:
        """Increment *stat* by *by* and return the new value."""
        key = stat.value
        self._counters[key] = self._counters.get(key, 0) + by
        return self._counters[key]

    def get(self, stat: MemoryMetricStat) -> int:
        """Return current value of *stat* (0 if not yet recorded)."""
        return self._counters.get(stat.value, 0)

    def reset(self, stat: MemoryMetricStat | None = None) -> None:
        """Reset *stat* to zero, or all stats if *stat* is None."""
        if stat is None:
            self._counters.clear()
        else:
            self._counters.pop(stat.value, None)

    def snapshot(self) -> Dict[str, int]:
        """Return a copy of all current counter values."""
        return dict(self._counters)

    def merge(self, other: "MemoryMetrics") -> None:
        """Add all counters from *other* into this instance."""
        for key, value in other._counters.items():
            self._counters[key] = self._counters.get(key, 0) + value

    def top_n(self, n: int = 5) -> List[tuple[str, int]]:
        """Return the top *n* stats by value, descending."""
        return sorted(self._counters.items(), key=lambda x: x[1], reverse=True)[:n]

    @property
    def total_events(self) -> int:
        return sum(self._counters.values())
