from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.db.session import SessionLocal
from app.ingestion.statuses import COMPLETED, COMPLETED_WITH_WARNINGS, FAILED, RUNNING
from app.models.entities import IngestionRun, SourceRegistry


def test_sources_coverage_returns_active_source_counts(client) -> None:
    unique_key = f"test_source_{uuid4().hex[:10]}"
    with SessionLocal() as db:
        db.add(
            SourceRegistry(
                source_key=unique_key,
                source_name="Test Coverage Source",
                source_type="court_record",
                source_tier="official",
                country="Canada",
                jurisdiction="CA-SK",
                is_active=True,
            )
        )
        db.commit()

    resp = client.get("/api/v1/sources/coverage")
    assert resp.status_code == 200  # nosec B101
    payload = resp.json()

    assert "total_active_sources" in payload  # nosec B101
    assert "coverage" in payload  # nosec B101
    assert isinstance(payload["coverage"], list)  # nosec B101

    match = next(
        (
            item
            for item in payload["coverage"]
            if item["country"] == "Canada"
            and item["jurisdiction"] == "CA-SK"
            and item["source_tier"] == "official"
        ),
        None,
    )
    assert match is not None  # nosec B101
    assert match["count"] >= 1  # nosec B101


def test_ingestion_status_returns_bucketed_window_summary(client) -> None:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        db.add_all(
            [
                IngestionRun(
                    source_name="test-source-running",
                    started_at=now - timedelta(minutes=20),
                    status=RUNNING,
                ),
                IngestionRun(
                    source_name="test-source-completed",
                    started_at=now - timedelta(minutes=15),
                    status=COMPLETED,
                ),
                IngestionRun(
                    source_name="test-source-completed-warn",
                    started_at=now - timedelta(minutes=10),
                    status=COMPLETED_WITH_WARNINGS,
                ),
                IngestionRun(
                    source_name="test-source-failed",
                    started_at=now - timedelta(minutes=5),
                    status=FAILED,
                ),
            ]
        )
        db.commit()

    resp = client.get("/api/v1/status/ingestion?window_hours=24")
    assert resp.status_code == 200  # nosec B101
    payload = resp.json()

    assert payload["window_hours"] == 24  # nosec B101
    assert payload["total_runs"] >= 4  # nosec B101
    assert payload["running"] >= 1  # nosec B101
    assert payload["completed"] >= 1  # nosec B101
    assert payload["completed_with_warnings"] >= 1  # nosec B101
    assert payload["failed"] >= 1  # nosec B101
    assert payload["last_run_at"] is not None  # nosec B101
    assert isinstance(payload["buckets"], list)  # nosec B101

    bucket_statuses = {b["status"] for b in payload["buckets"]}
    assert RUNNING in bucket_statuses  # nosec B101
    assert COMPLETED in bucket_statuses  # nosec B101
    assert COMPLETED_WITH_WARNINGS in bucket_statuses  # nosec B101
    assert FAILED in bucket_statuses  # nosec B101
