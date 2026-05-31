"""Tests for POST /api/admin/ingestion-runs/{run_id}/retry (Phase 6 hardening)."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.db.session import SessionLocal
from app.main import app
from app.models.entities import AuditLog, IngestionRun, SourceRegistry

client = TestClient(app)


def _admin_headers() -> dict[str, str]:
    from app.auth.jwt_handler import create_access_token
    token = create_access_token(email="admin@example.com", role="admin")
    return {"Authorization": f"Bearer {token}"}


class TestRetryEndpoint:
    """Unit-level tests for the retry endpoint."""

    def test_retry_run_not_found(self) -> None:
        """POST /api/admin/ingestion-runs/999999/retry returns 404 for unknown run."""
        with SessionLocal() as db:
            db.query(IngestionRun).filter(IngestionRun.id == 999999).delete()
            db.commit()

        response = client.post(
            "/api/admin/ingestion-runs/999999/retry",
            headers=_admin_headers(),
        )
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    def test_retry_run_succeeds(self) -> None:
        """Retry creates a new IngestionRun and returns run_id + source_key."""
        # Create a minimal SourceRegistry entry and a completed IngestionRun.
        with SessionLocal() as db:
            # Clean up any stale fixture data.
            db.query(IngestionRun).filter(
                IngestionRun.source_name == "_test_retry_src"
            ).delete()
            db.query(SourceRegistry).filter(
                SourceRegistry.source_key == "_test_retry_src"
            ).delete()
            db.commit()

            src = SourceRegistry(
                source_key="_test_retry_src",
                source_name="Test Retry Source",
                source_class="machine_ingest",
                parser="laws_justice_xml",
                parser_version="1.0",
                source_type="police",
                public_record_authority="municipal",
                allowed_domains='["example.com"]',
                base_url="https://example.com/feed",
                requires_manual_review=True,
                public_publish_default=False,
                automation_status="machine_ready_enabled",
                lifecycle_state="runnable",
                is_active=True,
            )
            db.add(src)
            db.commit()

            run = IngestionRun(
                source_name="_test_retry_src",
                started_at=datetime.now(timezone.utc),
                status="failed",
                fetched_count=0,
                error_count=1,
            )
            db.add(run)
            db.commit()
            run_id = run.id

        # Stub the adapter so no real HTTP call is made.
        fake_result = SimpleNamespace(
            records_fetched=3,
            records_skipped=0,
            created_records=[object(), object(), object()],
            review_items=[],
            errors=[],
            success=True,
        )
        fake_persist = SimpleNamespace(
            persisted_incidents=3,
            skipped_duplicates=0,
            persisted_review_items=0,
        )

        with (
            patch(
                "app.ingestion.source_adapter_factory.build_adapter",
                return_value=MagicMock(run=MagicMock(return_value=fake_result)),
            ),
            patch(
                "app.ingestion.source_runner.persist_ingestion_result",
                return_value=fake_persist,
            ),
            patch("app.ingestion.source_registry_ctl.update_source_health"),
            patch(
                "app.services.source_control.require_source_enabled",
                return_value=None,
            ),
        ):
            response = client.post(
                f"/api/admin/ingestion-runs/{run_id}/retry",
                headers=_admin_headers(),
            )

        assert response.status_code == 200, response.text
        data = response.json()
        assert data["source_key"] == "_test_retry_src"
        assert data["retried_run_id"] == run_id
        assert isinstance(data["new_run_id"], int)
        assert data["new_run_id"] != run_id
        assert data["run_id"] == data["new_run_id"]
        assert data["success"] is True
        assert data["created_records"] == 3

        with SessionLocal() as db:
            audit = (
                db.query(AuditLog)
                .filter(
                    AuditLog.action == "ingestion_run.retry",
                    AuditLog.entity_id == str(data["new_run_id"]),
                )
                .order_by(AuditLog.id.desc())
                .first()
            )
            assert audit is not None
            assert audit.actor_id == "admin@example.com"

        # Clean up.
        with SessionLocal() as db:
            db.query(IngestionRun).filter(
                IngestionRun.source_name == "_test_retry_src"
            ).delete()
            db.query(SourceRegistry).filter(
                SourceRegistry.source_key == "_test_retry_src"
            ).delete()
            db.commit()
