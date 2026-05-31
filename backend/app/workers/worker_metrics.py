"""Worker runtime metrics — per-job-type counters and throughput statistics."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass
class JobTypeStat:
    """Accumulated statistics for a single job type."""

    job_name: str
    total_enqueued: int = 0
    total_succeeded: int = 0
    total_failed: int = 0
    total_dead: int = 0
    total_retried: int = 0
    total_duration_seconds: float = 0.0

    @property
    def success_rate(self) -> float:
        """Fraction of completed jobs that succeeded.  Returns 0.0 if none ran."""
        completed = self.total_succeeded + self.total_failed + self.total_dead
        if completed == 0:
            return 0.0
        return self.total_succeeded / completed

    @property
    def avg_duration_seconds(self) -> float:
        """Mean execution time across successful runs."""
        if self.total_succeeded == 0:
            return 0.0
        return self.total_duration_seconds / self.total_succeeded


class WorkerMetrics:
    """Aggregate runtime metrics for the workers subsystem."""

    def __init__(self) -> None:
        self._stats: dict[str, JobTypeStat] = {}
        self._window_start = time.monotonic()
        self._total_enqueued = 0
        self._total_succeeded = 0
        self._total_failed = 0
        self._total_dead = 0

    # ------------------------------------------------------------------
    # Mutation helpers
    # ------------------------------------------------------------------

    def _stat(self, job_name: str) -> JobTypeStat:
        if job_name not in self._stats:
            self._stats[job_name] = JobTypeStat(job_name=job_name)
        return self._stats[job_name]

    def record_enqueued(self, job_name: str) -> None:
        self._stat(job_name).total_enqueued += 1
        self._total_enqueued += 1

    def record_success(self, job_name: str, duration_seconds: float) -> None:
        stat = self._stat(job_name)
        stat.total_succeeded += 1
        stat.total_duration_seconds += duration_seconds
        self._total_succeeded += 1

    def record_failure(self, job_name: str, *, dead: bool = False) -> None:
        stat = self._stat(job_name)
        if dead:
            stat.total_dead += 1
            self._total_dead += 1
        else:
            stat.total_failed += 1
            self._total_failed += 1

    def record_retry(self, job_name: str) -> None:
        self._stat(job_name).total_retried += 1

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def get_stat(self, job_name: str) -> JobTypeStat | None:
        return self._stats.get(job_name)

    def all_stats(self) -> list[JobTypeStat]:
        """Return per-job-type stats sorted by job name."""
        return sorted(self._stats.values(), key=lambda s: s.job_name)

    def summary(self) -> dict[str, Any]:
        """Return a high-level summary dict."""
        elapsed = time.monotonic() - self._window_start
        throughput = self._total_succeeded / elapsed if elapsed > 0 else 0.0
        return {
            "total_enqueued": self._total_enqueued,
            "total_succeeded": self._total_succeeded,
            "total_failed": self._total_failed,
            "total_dead": self._total_dead,
            "elapsed_seconds": round(elapsed, 3),
            "throughput_per_second": round(throughput, 6),
            "job_types": len(self._stats),
        }

    def reset(self) -> None:
        """Clear all counters and restart the elapsed window."""
        self._stats.clear()
        self._window_start = time.monotonic()
        self._total_enqueued = 0
        self._total_succeeded = 0
        self._total_failed = 0
        self._total_dead = 0
