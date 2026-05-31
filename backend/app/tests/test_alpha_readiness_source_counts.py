from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app.db.session import get_db
from app.db.session import SessionLocal
from app.main import app
from app.models.entities import SourceRegistry


client = TestClient(app)


def _make_source(source_key: str, lifecycle_state: str) -> SourceRegistry:
    return SourceRegistry(
        source_key=source_key,
        source_name=f"Source {source_key}",
        source_type="test",
        lifecycle_state=lifecycle_state,
        source_class="machine_ingest",
        is_active=lifecycle_state == "runnable",
        automation_status="machine_ready_enabled" if lifecycle_state == "runnable" else "machine_ready_disabled",
    )


def test_alpha_readiness_source_lifecycle_counts() -> None:
    keys = [
        "alpha-count-runnable",
        "alpha-count-enable-ready",
        "alpha-count-deprecated",
        "alpha-count-disabled-stub",
        "alpha-count-portal-reference",
    ]

    with SessionLocal() as db:
        db.query(SourceRegistry).filter(SourceRegistry.source_key.in_(keys)).delete(
            synchronize_session=False
        )
        db.add_all(
            [
                _make_source("alpha-count-runnable", "runnable"),
                _make_source("alpha-count-enable-ready", "runnable_disabled"),
                _make_source("alpha-count-deprecated", "deprecated"),
                _make_source("alpha-count-disabled-stub", "disabled_stub"),
                _make_source("alpha-count-portal-reference", "portal_reference"),
            ]
        )
        db.commit()

    try:
        response = client.get("/api/v1/status/alpha-readiness")
        assert response.status_code == 200
        payload = response.json()

        assert payload["runnable_sources"] >= 1
        assert payload["enable_ready_sources"] >= 1
        assert payload["deprecated_sources"] >= 1
    finally:
        with SessionLocal() as db:
            db.query(SourceRegistry).filter(SourceRegistry.source_key.in_(keys)).delete(
                synchronize_session=False
            )
            db.commit()


def test_alpha_readiness_graceful_when_source_registry_unavailable() -> None:
    class FailingSession:
        def scalar(self, _query):
            raise OperationalError(
                "select count(*) from source_registry",
                {},
                Exception("no such table: source_registry"),
            )

    def _override_get_db():
        yield FailingSession()

    app.dependency_overrides[get_db] = _override_get_db
    try:
        response = client.get("/api/v1/status/alpha-readiness")
        assert response.status_code == 200
        payload = response.json()

        assert payload["total_sources"] == 0
        assert payload["runnable_sources"] == 0
        assert payload["enable_ready_sources"] == 0
        assert payload["deprecated_sources"] == 0
        assert "source_registry_unavailable" in payload["warnings"]
        assert "database_not_migrated_or_unreachable" in payload["warnings"]
    finally:
        app.dependency_overrides.pop(get_db, None)
