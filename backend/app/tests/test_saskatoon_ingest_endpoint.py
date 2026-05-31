"""HTTP integration tests for POST /api/admin/ingest/saskatoon.

Verifies the full gate stack:
  1. settings.enable_admin_imports (via require_admin_imports dep)
  2. settings.local_feeds_enabled  (checked inside the endpoint)
  3. SourceRegistry.is_active       (checked by _check_source_active)

Fixture CSV: backend/app/ingestion/crime_sources/fixtures/saskatoon_sample.csv
             — 8 data rows, expected persisted_count == 8
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.main import app
from app.models.entities import CrimeIncident, SourceRegistry

client = TestClient(app)

_FIXTURE_CSV = (
    Path(__file__).parent.parent
    / "ingestion"
    / "crime_sources"
    / "fixtures"
    / "saskatoon_sample.csv"
)

def _jwt_admin_headers() -> dict:
    from app.auth.jwt_handler import create_access_token
    token = create_access_token(email="test-admin@example.test", role="admin")
    return {"Authorization": f"Bearer {token}"}

_ADMIN_HEADERS = _jwt_admin_headers


def _set_registry(db: Session, source_key: str, is_active: bool) -> None:
    status = "machine_ready_enabled" if is_active else "machine_ready_disabled"
    reg = db.query(SourceRegistry).filter_by(source_key=source_key).first()
    if reg is None:
        reg = SourceRegistry(
            source_key=source_key,
            source_name="saskatoon_police",
            source_tier="official",
            is_active=is_active,
            automation_status=status,
            requires_manual_review=True,
            auto_publish_enabled=False,
        )
        db.add(reg)
    else:
        reg.is_active = is_active
        reg.automation_status = status
    db.commit()


class TestSaskatoonIngestEndpoint:
    """Integration tests for the /api/admin/ingest/saskatoon endpoint."""

    def setup_method(self) -> None:
        """Enable both settings gates before each test."""
        os.environ["JTA_ENABLE_ADMIN_IMPORTS"] = "true"
        os.environ["JTA_LOCAL_FEEDS_ENABLED"] = "true"
        get_settings.cache_clear()
        # Pre-clean any leftover saskatoon rows from previous/other test modules
        with SessionLocal() as db:
            db.query(CrimeIncident).filter(
                CrimeIncident.source_id == "saskatoon_police"
            ).delete()
            db.commit()

    def teardown_method(self) -> None:
        """Restore defaults and purge any imported incidents."""
        os.environ.pop("JTA_ENABLE_ADMIN_IMPORTS", None)
        os.environ.pop("JTA_LOCAL_FEEDS_ENABLED", None)
        get_settings.cache_clear()
        with SessionLocal() as db:
            db.query(CrimeIncident).filter(
                CrimeIncident.source_id == "saskatoon_police"
            ).delete()
            db.commit()

    def test_happy_path_imports_all_rows(self) -> None:
        """Full pipeline: both flags on + active registry → 200, all 8 rows persisted."""
        with SessionLocal() as db:
            _set_registry(db, "saskatoon_open_data_crime", is_active=True)

        with _FIXTURE_CSV.open("rb") as fh:
            response = client.post(
                "/api/admin/ingest/saskatoon",
                headers=_ADMIN_HEADERS(),
                files={"file": ("saskatoon_sample.csv", fh, "text/csv")},
            )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["persisted_count"] == 8
        assert data["error_count"] == 0

        # All imported rows must be private and pending review
        with SessionLocal() as db:
            incidents = (
                db.query(CrimeIncident)
                .filter(CrimeIncident.source_id == "saskatoon_police")
                .all()
            )
        assert len(incidents) == 8
        for incident in incidents:
            assert incident.is_public is False, (
                f"Row {incident.id} should not be public after initial import"
            )
            assert incident.review_status == "pending_review", (
                f"Row {incident.id} should be pending_review, got {incident.review_status!r}"
            )

    def test_disabled_registry_returns_403(self) -> None:
        """Both settings flags on but source disabled in registry → 403."""
        with SessionLocal() as db:
            _set_registry(db, "saskatoon_open_data_crime", is_active=False)

        with _FIXTURE_CSV.open("rb") as fh:
            response = client.post(
                "/api/admin/ingest/saskatoon",
                headers=_ADMIN_HEADERS(),
                files={"file": ("saskatoon_sample.csv", fh, "text/csv")},
            )

        assert response.status_code == 403
        assert "disabled" in response.json().get("detail", "").lower()

    def test_local_feeds_disabled_returns_403(self) -> None:
        """enable_admin_imports=true but local_feeds_enabled=false → 403 before registry check."""
        os.environ.pop("JTA_LOCAL_FEEDS_ENABLED", None)
        get_settings.cache_clear()

        # Registry is active — gate must fire on the settings check, not the registry
        with SessionLocal() as db:
            _set_registry(db, "saskatoon_open_data_crime", is_active=True)

        with _FIXTURE_CSV.open("rb") as fh:
            response = client.post(
                "/api/admin/ingest/saskatoon",
                headers=_ADMIN_HEADERS(),
                files={"file": ("saskatoon_sample.csv", fh, "text/csv")},
            )

        assert response.status_code == 403
        detail = response.json().get("detail", "")
        assert "circuit breaker" in detail.lower() or "jta_local_feeds_enabled" in detail.lower()
