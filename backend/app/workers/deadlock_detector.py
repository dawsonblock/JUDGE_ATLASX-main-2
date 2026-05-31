"""Deadlock detector — tracks in-flight jobs and identifies stalled ones."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any


@dataclass
class InFlightRecord:
    """Tracks a job that has been dequeued and assigned to a worker."""

    job_id: str
    job_name: str
    worker_id: str
    started_at: float
    timeout_seconds: float
    attempt: int = 1


class DeadlockDetector:
    """Identifies jobs that have been running longer than their configured timeout."""

    def __init__(self) -> None:
        self._in_flight: dict[str, InFlightRecord] = {}

    def track(
        self,
        job_id: str,
        job_name: str,
        worker_id: str,
        timeout_seconds: float,
        *,
        attempt: int = 1,
    ) -> InFlightRecord:
        """Register *job_id* as currently in flight."""
        record = InFlightRecord(
            job_id=job_id,
            job_name=job_name,
            worker_id=worker_id,
            started_at=time.monotonic(),
            timeout_seconds=timeout_seconds,
            attempt=attempt,
        )
        self._in_flight[job_id] = record
        return record

    def complete(self, job_id: str) -> bool:
        """Remove *job_id* from in-flight tracking.  Returns ``True`` if found."""
        return self._in_flight.pop(job_id, None) is not None

    def stalled_jobs(self, now: float | None = None) -> list[InFlightRecord]:
        """Return records for jobs that have exceeded their timeout."""
        t = now if now is not None else time.monotonic()
        return [
            r
            for r in self._in_flight.values()
            if (t - r.started_at) > r.timeout_seconds
        ]

    def get_record(self, job_id: str) -> InFlightRecord | None:
        """Return the in-flight record for *job_id*, or ``None``."""
        return self._in_flight.get(job_id)

    def elapsed_seconds(self, job_id: str, now: float | None = None) -> float | None:
        """Return elapsed seconds for a tracked job, or ``None`` if not tracked."""
        record = self._in_flight.get(job_id)
        if record is None:
            return None
        t = now if now is not None else time.monotonic()
        return t - record.started_at

    def in_flight_count(self) -> int:
        """Return the number of currently tracked in-flight jobs."""
        return len(self._in_flight)

    def summary(self) -> dict[str, Any]:
        """Return a dict with in-flight and stalled counts."""
        stalled = self.stalled_jobs()
        return {
            "in_flight": len(self._in_flight),
            "stalled": len(stalled),
            "stalled_job_ids": [r.job_id for r in stalled],
        }
