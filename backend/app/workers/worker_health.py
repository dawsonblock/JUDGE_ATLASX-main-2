"""Worker health tracking via heartbeat records."""

from __future__ import annotations

import time
from dataclasses import dataclass
from enum import Enum
from typing import Any


class WorkerState(str, Enum):
    IDLE = "idle"
    BUSY = "busy"
    DEGRADED = "degraded"
    STOPPED = "stopped"


@dataclass
class WorkerBeat:
    """A single heartbeat snapshot for one worker."""

    worker_id: str
    state: WorkerState
    heartbeat_at: float
    current_job_id: str | None = None
    current_job_name: str | None = None
    jobs_completed: int = 0
    jobs_failed: int = 0


class WorkerHealthMonitor:
    """Tracks worker liveness through periodic heartbeat registration."""

    def __init__(self, stale_seconds: float = 60.0) -> None:
        self._beats: dict[str, WorkerBeat] = {}
        self._stale_seconds = stale_seconds

    def heartbeat(
        self,
        worker_id: str,
        state: WorkerState = WorkerState.IDLE,
        *,
        current_job_id: str | None = None,
        current_job_name: str | None = None,
        jobs_completed: int = 0,
        jobs_failed: int = 0,
    ) -> WorkerBeat:
        """Record a heartbeat.  Creates or overwrites the entry for *worker_id*."""
        beat = WorkerBeat(
            worker_id=worker_id,
            state=state,
            heartbeat_at=time.monotonic(),
            current_job_id=current_job_id,
            current_job_name=current_job_name,
            jobs_completed=jobs_completed,
            jobs_failed=jobs_failed,
        )
        self._beats[worker_id] = beat
        return beat

    def is_alive(self, worker_id: str) -> bool:
        """Return ``True`` if *worker_id* has sent a heartbeat within the stale window."""
        beat = self._beats.get(worker_id)
        if beat is None:
            return False
        return (time.monotonic() - beat.heartbeat_at) <= self._stale_seconds

    def get_beat(self, worker_id: str) -> WorkerBeat | None:
        """Return the last heartbeat for *worker_id*, or ``None``."""
        return self._beats.get(worker_id)

    def active_workers(self) -> list[WorkerBeat]:
        """Return beats for workers whose last heartbeat is within the stale window."""
        cutoff = time.monotonic() - self._stale_seconds
        return [b for b in self._beats.values() if b.heartbeat_at >= cutoff]

    def stale_workers(self) -> list[WorkerBeat]:
        """Return beats for workers whose last heartbeat exceeds the stale window."""
        cutoff = time.monotonic() - self._stale_seconds
        return [b for b in self._beats.values() if b.heartbeat_at < cutoff]

    def deregister(self, worker_id: str) -> bool:
        """Remove *worker_id* from tracking.  Returns ``True`` if it was present."""
        return self._beats.pop(worker_id, None) is not None

    def summary(self) -> dict[str, Any]:
        """Return a dict with active/stale/busy/idle counts."""
        active = self.active_workers()
        stale = self.stale_workers()
        busy = [b for b in active if b.state == WorkerState.BUSY]
        return {
            "active": len(active),
            "stale": len(stale),
            "busy": len(busy),
            "idle": len(active) - len(busy),
        }

    def __len__(self) -> int:
        return len(self._beats)
