from __future__ import annotations

import time

from fastapi.testclient import TestClient

from app.auth.jwt_handler import create_access_token
from app.main import app
from app.workers.queue_backend import IngestionJobRecord, JobState


client = TestClient(app)


def _admin_headers(role: str = "admin") -> dict[str, str]:
    token = create_access_token(email="admin@example.com", role=role)
    return {"Authorization": f"Bearer {token}"}


class _FakeQueue:
    def __init__(self) -> None:
        self._records: dict[str, IngestionJobRecord] = {
            "job-1": IngestionJobRecord(job_id="job-1", source_key="source_a"),
            "job-2": IngestionJobRecord(
                job_id="job-2",
                source_key="source_b",
                state=JobState.COMPLETED,
                run_id=10,
            ),
        }
        self._pending = ["job-1"]

    def enqueue(self, source_key: str) -> str:
        new_id = f"job-{len(self._records) + 1}"
        self._records[new_id] = IngestionJobRecord(job_id=new_id, source_key=source_key)
        self._pending.append(new_id)
        return new_id

    def run_next(self) -> IngestionJobRecord | None:
        return None

    def run_job(self, job_id: str) -> IngestionJobRecord | None:
        return self._records.get(job_id)

    def get_status(self, job_id: str) -> IngestionJobRecord | None:
        return self._records.get(job_id)

    def list_jobs(self, state: JobState | None = None) -> list[IngestionJobRecord]:
        records = list(self._records.values())
        if state is not None:
            records = [r for r in records if r.state == state]
        return records

    def pending_count(self) -> int:
        return len(self._pending)

    def cancel_job(self, job_id: str, error: str = "Canceled by admin") -> IngestionJobRecord | None:
        record = self._records.get(job_id)
        if record is None:
            return None
        if record.state in (JobState.COMPLETED, JobState.FAILED):
            raise ValueError(f"Job '{job_id}' is already {record.state.value} and cannot be canceled.")
        if job_id in self._pending:
            self._pending.remove(job_id)
        record.state = JobState.FAILED
        record.error = error
        record.finished_at = time.time()
        return record

    def retry_job(self, job_id: str) -> str | None:
        record = self._records.get(job_id)
        if record is None:
            return None
        if record.state not in (JobState.FAILED, JobState.COMPLETED):
            raise ValueError(f"Job '{job_id}' must be completed or failed before retry.")
        return self.enqueue(record.source_key)


def test_list_ingestion_jobs(monkeypatch) -> None:
    from app.api.routes import admin_ingestion_jobs

    fake_queue = _FakeQueue()
    monkeypatch.setattr(admin_ingestion_jobs, "get_ingestion_queue", lambda: fake_queue)

    response = client.get("/api/admin/ingestion-jobs", headers=_admin_headers())

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) == 2
    assert {entry["job_id"] for entry in payload} == {"job-1", "job-2"}


def test_get_ingestion_job_by_id(monkeypatch) -> None:
    from app.api.routes import admin_ingestion_jobs

    fake_queue = _FakeQueue()
    monkeypatch.setattr(admin_ingestion_jobs, "get_ingestion_queue", lambda: fake_queue)

    response = client.get("/api/admin/ingestion-jobs/job-1", headers=_admin_headers())

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_id"] == "job-1"
    assert payload["source_key"] == "source_a"
    assert payload["state"] == "pending"


def test_cancel_ingestion_job(monkeypatch) -> None:
    from app.api.routes import admin_ingestion_jobs

    fake_queue = _FakeQueue()
    monkeypatch.setattr(admin_ingestion_jobs, "get_ingestion_queue", lambda: fake_queue)

    response = client.post(
        "/api/admin/ingestion-jobs/job-1/cancel",
        headers=_admin_headers(role="source_admin"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["job_id"] == "job-1"
    assert payload["state"] == "failed"
    assert payload["error"] == "Canceled by admin"


def test_retry_ingestion_job(monkeypatch) -> None:
    from app.api.routes import admin_ingestion_jobs

    fake_queue = _FakeQueue()
    monkeypatch.setattr(admin_ingestion_jobs, "get_ingestion_queue", lambda: fake_queue)

    response = client.post(
        "/api/admin/ingestion-jobs/job-2/retry",
        headers=_admin_headers(role="source_admin"),
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["old_job_id"] == "job-2"
    assert payload["source_key"] == "source_b"
    assert payload["new_job_id"] in fake_queue._records
