"""In-process ingestion queue backend.

This backend is suitable for alpha/single-process operation only.
"""
from __future__ import annotations

import logging
import threading
import time
import uuid

from app.workers.queue_backend import (
    IngestionJobRecord,
    JobState,
    QueueBackendCapabilities,
)

logger = logging.getLogger(__name__)


class InProcessIngestionQueue:
    """Thread-safe in-process ingestion queue.

    Jobs are executed synchronously when ``run_next()`` is called.
    Alpha-only backend; not production-capable.
    """

    def __init__(self, max_history: int = 500) -> None:
        self._lock = threading.Lock()
        self._pending: list[str] = []
        self._records: dict[str, IngestionJobRecord] = {}
        self._max_history = max_history
        self._capabilities = QueueBackendCapabilities(
            name="inprocess",
            supports_production=False,
            implementation_status="alpha",
        )

    def enqueue(self, source_key: str) -> str:
        job_id = str(uuid.uuid4())
        record = IngestionJobRecord(job_id=job_id, source_key=source_key)
        with self._lock:
            self._records[job_id] = record
            self._pending.append(job_id)
        logger.info("Enqueued ingestion job %s for source %s", job_id, source_key)
        return job_id

    def run_next(self) -> IngestionJobRecord | None:
        from app.workers.jobs.ingestion_run import run_ingestion_job

        with self._lock:
            if not self._pending:
                return None
            job_id = self._pending.pop(0)
            record = self._records[job_id]
            record.state = JobState.RUNNING
            record.started_at = time.time()

        logger.info("Starting ingestion job %s for source %s", job_id, record.source_key)

        try:
            result = run_ingestion_job({"source_key": record.source_key})
        except Exception as exc:  # noqa: BLE001
            logger.exception("Ingestion job %s failed with exception", job_id)
            with self._lock:
                record.state = JobState.FAILED
                record.finished_at = time.time()
                record.error = str(exc)
            return record

        with self._lock:
            record.finished_at = time.time()
            record.result = result
            if result.get("ok"):
                record.state = JobState.COMPLETED
                record.run_id = result.get("run_id")
                record.records_fetched = result.get("records_fetched", 0)
                record.review_items = result.get("review_items", 0)
                record.created_records = result.get("created_records", 0)
                record.raw_snapshot_preserved = result.get("raw_snapshot_preserved", False)
            else:
                record.state = JobState.FAILED
                record.error = result.get("message", "Unknown error")

        logger.info(
            "Ingestion job %s finished: state=%s records=%d",
            job_id,
            record.state.value,
            record.records_fetched,
        )
        self._evict_old_records()
        return record

    def run_job(self, job_id: str) -> IngestionJobRecord | None:
        with self._lock:
            record = self._records.get(job_id)
            if record is None or record.state != JobState.PENDING:
                return record
            if job_id in self._pending:
                self._pending.remove(job_id)
                self._pending.insert(0, job_id)

        return self.run_next()

    def get_status(self, job_id: str) -> IngestionJobRecord | None:
        with self._lock:
            return self._records.get(job_id)

    def list_jobs(self, state: JobState | None = None) -> list[IngestionJobRecord]:
        with self._lock:
            records = list(self._records.values())
        if state is not None:
            records = [r for r in records if r.state == state]
        return sorted(records, key=lambda r: r.enqueued_at, reverse=True)

    def pending_count(self) -> int:
        with self._lock:
            return len(self._pending)

    def cancel_job(self, job_id: str, error: str = "Canceled by admin") -> IngestionJobRecord | None:
        with self._lock:
            record = self._records.get(job_id)
            if record is None:
                return None
            if record.state in (JobState.COMPLETED, JobState.FAILED):
                raise ValueError(
                    f"Job '{job_id}' is already {record.state.value} and cannot be canceled."
                )
            if job_id in self._pending:
                self._pending.remove(job_id)
                record.state = JobState.CANCELLED
            record.error = error
            record.finished_at = time.time()
            return record

    def retry_job(self, job_id: str) -> str | None:
        with self._lock:
            record = self._records.get(job_id)
            if record is None:
                return None
            if record.state not in (
                JobState.COMPLETED,
                JobState.FAILED,
                JobState.CANCELLED,
            ):
                raise ValueError(
                    f"Job '{job_id}' must be completed, failed, or cancelled before retry."
                )
            new_job_id = str(uuid.uuid4())
            new_record = IngestionJobRecord(job_id=new_job_id, source_key=record.source_key)
            self._records[new_job_id] = new_record
            self._pending.append(new_job_id)
            return new_job_id

    def _evict_old_records(self) -> None:
        with self._lock:
            finished = [
                r
                for r in self._records.values()
                if r.state in (
                    JobState.COMPLETED,
                    JobState.FAILED,
                    JobState.CANCELLED,
                )
            ]
            if len(finished) > self._max_history:
                finished.sort(key=lambda r: r.finished_at or 0)
                to_remove = finished[: len(finished) - self._max_history]
                for r in to_remove:
                    del self._records[r.job_id]
