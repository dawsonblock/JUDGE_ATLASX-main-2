"""Shared ingestion queue backend types and interfaces."""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, Literal


class JobState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class QueueBackendCapabilities:
    """Describes the capabilities and production readiness of a queue backend."""

    name: str
    supports_production: bool
    implementation_status: Literal["alpha", "placeholder", "production_ready"]


@dataclass
class IngestionJobRecord:
    """Tracks the state of a single ingestion job."""

    job_id: str
    source_key: str
    state: JobState = JobState.PENDING
    enqueued_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None
    run_id: int | None = None
    records_fetched: int = 0
    review_items: int = 0
    created_records: int = 0
    raw_snapshot_preserved: bool = False
    error: str | None = None
    result: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "source_key": self.source_key,
            "state": self.state.value,
            "enqueued_at": self.enqueued_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "run_id": self.run_id,
            "records_fetched": self.records_fetched,
            "review_items": self.review_items,
            "created_records": self.created_records,
            "raw_snapshot_preserved": self.raw_snapshot_preserved,
            "error": self.error,
        }


class IngestionQueueBackend(Protocol):
    """Backend interface for ingestion queue lifecycle operations."""

    def enqueue(self, source_key: str) -> str:
        ...

    def run_next(self) -> IngestionJobRecord | None:
        ...

    def run_job(self, job_id: str) -> IngestionJobRecord | None:
        ...

    def get_status(self, job_id: str) -> IngestionJobRecord | None:
        ...

    def list_jobs(self, state: JobState | None = None) -> list[IngestionJobRecord]:
        ...

    def pending_count(self) -> int:
        ...

    def cancel_job(self, job_id: str, error: str = "Canceled by admin") -> IngestionJobRecord | None:
        ...

    def retry_job(self, job_id: str) -> str | None:
        ...
