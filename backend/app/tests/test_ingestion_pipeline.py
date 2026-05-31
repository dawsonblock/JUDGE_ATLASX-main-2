"""Tests for the ingestion pipeline formalization (Phase G).

Covers:
- quarantine_run / list_quarantined / release_from_quarantine service layer
- Admin quarantine API routes
- runner.py pipeline_stage transitions (via unit-level inspection)
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from app.db.session import Base, SessionLocal
from app.ingestion.quarantine import (
    list_quarantined,
    quarantine_run,
    release_from_quarantine,
)
from app.main import app
from app.models.entities import IngestionRun

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _make_run(
    db: Session, *, source: str = "test_source", status: str = "running"
) -> IngestionRun:
    run = IngestionRun(
        source_name=source,
        started_at=_now(),
        status=status,
        errors=[],
    )
    db.add(run)
    db.flush()
    return run


def _admin_headers() -> dict[str, str]:
    from app.auth.jwt_handler import create_access_token
    token = create_access_token(email="admin@example.com", role="admin")
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Fixture: in-memory SQLite session (isolated from shared test.db)
# ---------------------------------------------------------------------------


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def _set_pragma(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


# ---------------------------------------------------------------------------
# quarantine_run
# ---------------------------------------------------------------------------


class TestQuarantineRun:
    def test_sets_pipeline_stage(self, db):
        run = _make_run(db)
        quarantine_run(db, run, "unit test reason")
        assert run.pipeline_stage == "quarantine"

    def test_sets_quarantine_reason(self, db):
        run = _make_run(db)
        quarantine_run(db, run, "validation failed: missing defendant")
        assert run.quarantine_reason == "validation failed: missing defendant"

    def test_sets_status_failed(self, db):
        run = _make_run(db)
        quarantine_run(db, run, "error")
        assert run.status == "failed"

    def test_does_not_commit(self, db):
        # After quarantine_run, changes should be flushed but not committed;
        # rolling back should undo them.
        run = _make_run(db)
        quarantine_run(db, run, "pending")
        db.rollback()
        # After rollback run is expired; re-fetching confirms state was not persisted
        refreshed = db.get(IngestionRun, run.id)
        assert refreshed is None or refreshed.pipeline_stage != "quarantine"


# ---------------------------------------------------------------------------
# list_quarantined
# ---------------------------------------------------------------------------


class TestListQuarantined:
    def test_returns_only_quarantined(self, db):
        q_run = _make_run(db, source="source_a")
        ok_run = _make_run(db, source="source_b", status="completed")
        quarantine_run(db, q_run, "suspicious")
        db.flush()

        results = list_quarantined(db)
        result_ids = [r.id for r in results]
        assert q_run.id in result_ids
        assert ok_run.id not in result_ids

    def test_empty_when_none_quarantined(self, db):
        _make_run(db, status="completed")
        db.flush()
        assert list_quarantined(db) == []

    def test_multiple_quarantined(self, db):
        r1 = _make_run(db, source="s1")
        r2 = _make_run(db, source="s2")
        quarantine_run(db, r1, "reason-1")
        quarantine_run(db, r2, "reason-2")
        db.flush()

        results = list_quarantined(db)
        assert len(results) == 2

    def test_ordered_most_recent_first(self, db):
        r1 = _make_run(db, source="early")
        r2 = _make_run(db, source="late")
        quarantine_run(db, r1, "r1")
        quarantine_run(db, r2, "r2")
        db.flush()

        results = list_quarantined(db)
        # r2 was started later (inserted second); should appear first
        assert results[0].id == r2.id


# ---------------------------------------------------------------------------
# release_from_quarantine
# ---------------------------------------------------------------------------


class TestReleaseFromQuarantine:
    def test_happy_path_clears_fields(self, db):
        run = _make_run(db)
        quarantine_run(db, run, "test")
        db.flush()

        released = release_from_quarantine(db, run.id)
        assert released.pipeline_stage is None
        assert released.quarantine_reason is None

    def test_sets_status_released(self, db):
        run = _make_run(db)
        quarantine_run(db, run, "reason")
        db.flush()

        released = release_from_quarantine(db, run.id)
        assert released.status == "released"

    def test_returns_ingestion_run(self, db):
        run = _make_run(db)
        quarantine_run(db, run, "x")
        db.flush()

        result = release_from_quarantine(db, run.id)
        assert isinstance(result, IngestionRun)
        assert result.id == run.id

    def test_not_found_raises_value_error(self, db):
        with pytest.raises(ValueError, match="not found"):
            release_from_quarantine(db, 999_999)

    def test_not_quarantined_raises_value_error(self, db):
        run = _make_run(db, status="completed")
        db.flush()

        with pytest.raises(ValueError):
            release_from_quarantine(db, run.id)


# ---------------------------------------------------------------------------
# Admin quarantine API routes (integration — uses shared app + SessionLocal)
# ---------------------------------------------------------------------------


client = TestClient(app)


class TestAdminQuarantineRoutes:
    """Integration tests against the real FastAPI app and SQLite test.db."""

    def _create_quarantined_run(self, reason: str = "automated test") -> int:
        with SessionLocal() as db:
            run = IngestionRun(
                source_name="test_quarantine_source",
                started_at=_now(),
                status="failed",
                pipeline_stage="quarantine",
                quarantine_reason=reason,
                errors=[],
            )
            db.add(run)
            db.commit()
            return run.id

    def test_list_quarantined_returns_200(self):
        response = client.get("/api/admin/quarantine", headers=_admin_headers())
        assert response.status_code == 200

    def test_list_quarantined_returns_list(self):
        response = client.get("/api/admin/quarantine", headers=_admin_headers())
        assert isinstance(response.json(), list)

    def test_list_includes_quarantined_run(self):
        run_id = self._create_quarantined_run("api list test")
        response = client.get("/api/admin/quarantine", headers=_admin_headers())
        assert response.status_code == 200
        ids = [r["id"] for r in response.json()]
        assert run_id in ids

    def test_list_requires_auth(self):
        response = client.get("/api/admin/quarantine")
        assert response.status_code in (401, 403)

    def test_release_happy_path(self):
        run_id = self._create_quarantined_run("release test")
        response = client.post(
            f"/api/admin/quarantine/{run_id}/release",
            headers=_admin_headers(),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["id"] == run_id
        assert body["status"] == "released"
        assert body["pipeline_stage"] is None

    def test_release_not_found_returns_404(self):
        response = client.post(
            "/api/admin/quarantine/999999/release",
            headers=_admin_headers(),
        )
        assert response.status_code == 404

    def test_release_requires_auth(self):
        run_id = self._create_quarantined_run("auth test")
        response = client.post(f"/api/admin/quarantine/{run_id}/release")
        assert response.status_code in (401, 403)

    def test_release_non_quarantined_returns_422(self):
        with SessionLocal() as db:
            run = IngestionRun(
                source_name="not_quarantined",
                started_at=_now(),
                status="completed",
                errors=[],
            )
            db.add(run)
            db.commit()
            run_id = run.id

        response = client.post(
            f"/api/admin/quarantine/{run_id}/release",
            headers=_admin_headers(),
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# runner.py pipeline_stage transitions
# ---------------------------------------------------------------------------


class TestRunnerPipelineStages:
    """Verify that the ingestion runner advances pipeline_stage correctly."""

    def _build_mock_adapter(
        self, records=(), *, fetch_raises=False, adapter_errors=None
    ):
        adapter = MagicMock()
        adapter.errors = adapter_errors or []
        if fetch_raises:
            adapter.fetch.side_effect = RuntimeError("fetch failure")
        else:
            adapter.fetch.return_value = list(records)
        adapter.parse_many.return_value = []  # no-op parse
        return adapter

    def test_stage_complete_on_success(self):
        """A clean run ends with pipeline_stage='complete'."""
        from app.ingestion.runner import run_courtlistener_ingestion

        with SessionLocal() as db:
            with (
                patch("app.ingestion.runner.CourtListenerAdapter") as MockAdapter,
                patch("app.ingestion.runner.advisory_lock") as mock_lock,
                patch(
                    "app.ingestion.runner.check_ingestion_allowed",
                    return_value=(True, None),
                ),
                patch("app.ingestion.runner.require_source_registry") as mock_registry,
                patch("app.ingestion.runner.update_source_health"),
            ):
                mock_lock.return_value.__enter__ = lambda s: True
                mock_lock.return_value.__exit__ = MagicMock(return_value=False)
                mock_registry.return_value.id = 1
                MockAdapter.return_value = self._build_mock_adapter()

                run = run_courtlistener_ingestion(db, _now())

        assert run.pipeline_stage == "complete"

    def test_stage_fetch_failure_does_not_reach_complete(self):
        """When adapter.fetch raises, the run never reaches pipeline_stage='complete'."""
        from app.ingestion.runner import run_courtlistener_ingestion

        with SessionLocal() as db:
            with (
                patch("app.ingestion.runner.CourtListenerAdapter") as MockAdapter,
                patch("app.ingestion.runner.advisory_lock") as mock_lock,
                patch(
                    "app.ingestion.runner.check_ingestion_allowed",
                    return_value=(True, None),
                ),
                patch("app.ingestion.runner.require_source_registry") as mock_registry,
                patch("app.ingestion.runner.update_source_health"),
            ):
                mock_lock.return_value.__enter__ = lambda s: True
                mock_lock.return_value.__exit__ = MagicMock(return_value=False)
                mock_registry.return_value.id = 1
                MockAdapter.return_value = self._build_mock_adapter(fetch_raises=True)

                run = run_courtlistener_ingestion(db, _now())

        assert run.pipeline_stage != "complete"
