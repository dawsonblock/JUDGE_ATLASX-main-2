"""Job execution result container and in-memory result store."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    RETRY = "retry"
    DEAD = "dead"  # retries exhausted


@dataclass
class JobResult:
    """Immutable snapshot of a completed (or failed) job execution."""

    job_id: str
    job_name: str
    status: JobStatus
    attempt: int
    started_at: float
    finished_at: float
    output: Any = None
    error: str | None = None
    traceback: str | None = None

    @property
    def duration_seconds(self) -> float:
        return self.finished_at - self.started_at

    @property
    def succeeded(self) -> bool:
        return self.status == JobStatus.SUCCESS

    @property
    def failed(self) -> bool:
        return self.status in (JobStatus.FAILURE, JobStatus.DEAD)


class ResultStore:
    """In-memory ring-buffer store for recent JobResult objects."""

    def __init__(self, max_size: int = 1000) -> None:
        self._results: dict[str, list[JobResult]] = {}
        self._max_size = max_size
        self._all: list[JobResult] = []

    def record(self, result: JobResult) -> None:
        """Store *result*.  Evicts the oldest entry when the buffer is full."""
        if len(self._all) >= self._max_size:
            oldest = self._all.pop(0)
            history = self._results.get(oldest.job_id, [])
            if history and history[0] is oldest:
                history.pop(0)
        self._all.append(result)
        self._results.setdefault(result.job_id, []).append(result)

    def get_latest(self, job_id: str) -> JobResult | None:
        """Return the most recent result for *job_id*, or ``None``."""
        history = self._results.get(job_id)
        return history[-1] if history else None

    def get_history(self, job_id: str) -> list[JobResult]:
        """Return all recorded results for *job_id*, oldest first."""
        return list(self._results.get(job_id, []))

    def list_by_status(self, status: JobStatus) -> list[JobResult]:
        """Return all stored results matching *status*."""
        return [r for r in self._all if r.status == status]

    def recent(self, n: int = 50) -> list[JobResult]:
        """Return up to *n* most recent results (newest last)."""
        return list(self._all[-n:])

    def __len__(self) -> int:
        return len(self._all)
