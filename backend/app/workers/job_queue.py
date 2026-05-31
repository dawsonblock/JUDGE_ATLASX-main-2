"""In-process priority job queue backed by a binary heap."""

from __future__ import annotations

import heapq
import threading
import time
import uuid
from dataclasses import dataclass
from enum import IntEnum
from typing import Any


class Priority(IntEnum):
    CRITICAL = 1
    HIGH = 2
    NORMAL = 5
    LOW = 8
    BACKGROUND = 10


@dataclass
class JobEnvelope:
    """A job payload bundled with scheduling metadata."""

    job_id: str
    job_name: str
    payload: dict[str, Any]
    priority: int
    enqueued_at: float
    attempt: int = 0

    # Heap ordering: compare by (priority, enqueued_at) so lower priority
    # int wins, and ties break by earliest enqueue time.
    def __lt__(self, other: "JobEnvelope") -> bool:
        return (self.priority, self.enqueued_at) < (other.priority, other.enqueued_at)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, JobEnvelope):
            return NotImplemented
        return self.job_id == other.job_id


class JobQueue:
    """Thread-safe priority min-heap job queue."""

    def __init__(self) -> None:
        self._heap: list[JobEnvelope] = []
        self._lock = threading.Lock()
        self._id_set: set[str] = set()

    def enqueue(
        self,
        job_name: str,
        payload: dict[str, Any],
        *,
        priority: int = Priority.NORMAL,
        job_id: str | None = None,
    ) -> str:
        """Add a job to the queue.  Returns the job_id."""
        job_id = job_id or str(uuid.uuid4())
        env = JobEnvelope(
            job_id=job_id,
            job_name=job_name,
            payload=payload,
            priority=priority,
            enqueued_at=time.monotonic(),
        )
        with self._lock:
            if job_id in self._id_set:
                raise ValueError(f"Duplicate job_id: {job_id!r}")
            heapq.heappush(self._heap, env)
            self._id_set.add(job_id)
        return job_id

    def dequeue(self) -> JobEnvelope | None:
        """Remove and return the highest-priority job, or ``None`` if empty."""
        with self._lock:
            if not self._heap:
                return None
            env = heapq.heappop(self._heap)
            self._id_set.discard(env.job_id)
            return env

    def peek(self) -> JobEnvelope | None:
        """Return the highest-priority job *without* removing it."""
        with self._lock:
            return self._heap[0] if self._heap else None

    def is_empty(self) -> bool:
        """Return ``True`` if the queue has no items."""
        return len(self) == 0

    def clear(self) -> int:
        """Drain the queue.  Returns the number of items removed."""
        with self._lock:
            count = len(self._heap)
            self._heap.clear()
            self._id_set.clear()
            return count

    def __len__(self) -> int:
        with self._lock:
            return len(self._heap)
