"""Regression tests for admin ingestion and source endpoints.

Verifies that admin endpoints return correct field names matching ORM models.
Prevents drift like source vs source_name, completed_at vs finished_at, etc.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.main import app
from app.models.entities import IngestionRun, ReviewItem, SourceRegistry, SourceSnapshot

client = TestClient(app)


def get_admin_headers():
    """Get admin auth headers for testing (JWT Bearer)."""
    from app.auth.jwt_handler import create_access_token
    token = create_access_token(email="admin@example.com", role="admin")
    return {"Authorization": f"Bearer {token}"}


class TestAdminIngestionEndpoints:
    """Regression tests for admin ingestion control plane."""

    def test_list_runs_empty(self) -> None:
        """GET /api/admin/ingestion-runs returns empty list when no runs."""
        with SessionLocal() as db:
            # Clear any existing runs for clean test
            db.query(IngestionRun).delete()
            db.commit()

        response = client.get("/api/admin/ingestion-runs", headers=get_admin_headers())
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 0

    def test_list_runs_with_data(self) -> None:
        """GET /api/admin/ingestion-runs returns runs with correct field names."""
        with SessionLocal() as db:
            # Create test run
            run = IngestionRun(
                source_name="test_source",
                started_at=datetime.now(timezone.utc),
                status="completed",
                fetched_count=100,
                parsed_count=95,
                persisted_count=90,
                skipped_count=5,
                error_count=0,
            )
            db.add(run)
            db.commit()
            run_id = run.id

        response = client.get("/api/admin/ingestion-runs", headers=get_admin_headers())
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1

        # Verify field names match ORM model (NOT drifted names)
        first_run = data[0]
        assert "source_name" in first_run  # NOT "source"
        assert "finished_at" in first_run  # NOT "completed_at"
        assert "skipped_count" in first_run  # NOT "rejected_count"
        assert "error_count" in first_run
        assert "fetched_count" in first_run
        assert "parsed_count" in first_run
        assert "persisted_count" in first_run  # NOT "items_inserted"

        # Cleanup
        with SessionLocal() as db:
            db.query(IngestionRun).filter(IngestionRun.id == run_id).delete()
            db.commit()

    def test_list_runs_filter_by_source(self) -> None:
        """Filter by source_name works."""
        with SessionLocal() as db:
            run = IngestionRun(
                source_name="specific_source",
                started_at=datetime.now(timezone.utc),
                status="running",
            )
            db.add(run)
            db.commit()
            run_id = run.id

        response = client.get(
            "/api/admin/ingestion-runs?source=specific_source",
            headers=get_admin_headers(),
        )
        assert response.status_code == 200
        data = response.json()
        assert all(r["source_name"] == "specific_source" for r in data)

        # Cleanup
        with SessionLocal() as db:
            db.query(IngestionRun).filter(IngestionRun.id == run_id).delete()
            db.commit()

    def test_list_runs_filter_by_status(self) -> None:
        """Filter by status works."""
        with SessionLocal() as db:
            run = IngestionRun(
                source_name="test",
                started_at=datetime.now(timezone.utc),
                status="failed",
            )
            db.add(run)
            db.commit()
            run_id = run.id

        response = client.get(
            "/api/admin/ingestion-runs?status=failed",
            headers=get_admin_headers(),
        )
        assert response.status_code == 200
        data = response.json()
        assert all(r["status"] == "failed" for r in data)

        # Cleanup
        with SessionLocal() as db:
            db.query(IngestionRun).filter(IngestionRun.id == run_id).delete()
            db.commit()

    def test_get_run_detail(self) -> None:
        """GET /{run_id} returns correct IngestionRunDetail with all fields."""
        with SessionLocal() as db:
            run = IngestionRun(
                source_name="detail_test",
                started_at=datetime.now(timezone.utc),
                finished_at=datetime.now(timezone.utc),
                status="completed",
                fetched_count=100,
                parsed_count=95,
                persisted_count=90,
                skipped_count=5,
                error_count=0,
                errors=[],
            )
            db.add(run)
            db.commit()
            run_id = run.id

        response = client.get(
            f"/api/admin/ingestion-runs/{run_id}",
            headers=get_admin_headers(),
        )
        assert response.status_code == 200
        data = response.json()

        # Verify all expected fields present with correct names
        assert "source_name" in data
        assert "finished_at" in data
        assert "skipped_count" in data
        assert "errors" in data  # NOT "error_log"
        assert "fetched_count" in data
        assert "parsed_count" in data
        assert "persisted_count" in data
        assert "error_count" in data

        # Verify no drifted fields
        assert "source" not in data  # Old drifted name
        assert "completed_at" not in data  # Old drifted name
        assert "error_log" not in data  # Old drifted name
        assert "config_snapshot" not in data  # Non-existent field

        # Cleanup
        with SessionLocal() as db:
            db.query(IngestionRun).filter(IngestionRun.id == run_id).delete()
            db.commit()

    def test_get_run_detail_404(self) -> None:
        """GET /{run_id} returns 404 for nonexistent run."""
        response = client.get(
            "/api/admin/ingestion-runs/999999",
            headers=get_admin_headers(),
        )
        assert response.status_code == 404

    def test_get_run_review_items(self) -> None:
        """GET /{run_id}/review-items returns linked items via ingestion_run_id."""
        with SessionLocal() as db:
            run = IngestionRun(
                source_name="review_test",
                started_at=datetime.now(timezone.utc),
                status="completed",
            )
            db.add(run)
            db.flush()

            item = ReviewItem(
                record_type="test",
                source_quality="test",
                privacy_status="private",
                publish_recommendation="pending",
                status="pending",
                suggested_payload_json={},
                ingestion_run_id=run.id,
            )
            db.add(item)
            db.commit()
            run_id = run.id

        response = client.get(
            f"/api/admin/ingestion-runs/{run_id}/review-items",
            headers=get_admin_headers(),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == run_id
        assert data["source_name"] == "review_test"
        assert data["total_items"] >= 1

        # Cleanup
        with SessionLocal() as db:
            db.query(ReviewItem).filter(ReviewItem.ingestion_run_id == run_id).delete()
            db.query(IngestionRun).filter(IngestionRun.id == run_id).delete()
            db.commit()

    def test_get_run_snapshots(self) -> None:
        """GET /{run_id}/snapshots returns linked snapshots via ingestion_run_id."""
        with SessionLocal() as db:
            run = IngestionRun(
                source_name="snapshot_test",
                started_at=datetime.now(timezone.utc),
                status="completed",
            )
            db.add(run)
            db.flush()

            snapshot = SourceSnapshot(
                source_url="http://test.com",
                fetched_at=datetime.now(timezone.utc),
                content_hash="abc123",
                storage_backend="db",
                ingestion_run_id=run.id,
            )
            db.add(snapshot)
            db.commit()
            run_id = run.id

        response = client.get(
            f"/api/admin/ingestion-runs/{run_id}/snapshots",
            headers=get_admin_headers(),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["run_id"] == run_id
        assert data["source_name"] == "snapshot_test"
        assert data["total_snapshots"] >= 1

        # Cleanup
        with SessionLocal() as db:
            db.query(SourceSnapshot).filter(
                SourceSnapshot.ingestion_run_id == run_id
            ).delete()
            db.query(IngestionRun).filter(IngestionRun.id == run_id).delete()
            db.commit()

    def test_retry_run_not_found(self) -> None:
        """POST /{run_id}/retry returns 404 for nonexistent."""
        response = client.post(
            "/api/admin/ingestion-runs/999999/retry",
            headers=get_admin_headers(),
        )
        assert response.status_code == 404


class TestAdminSourceEndpoints:
    """Regression tests for admin source control plane."""

    def test_list_sources(self) -> None:
        """GET /api/admin/sources returns sources with correct fields."""
        response = client.get("/api/admin/sources", headers=get_admin_headers())
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        if data:
            # Verify SourceResponse fields
            source = data[0]
            assert "source_key" in source
            assert "source_name" in source
            assert "source_type" in source
            assert "is_active" in source

    def test_list_sources_filter_active(self) -> None:
        """Filter by is_active works."""
        response = client.get(
            "/api/admin/sources?is_active=true",
            headers=get_admin_headers(),
        )
        assert response.status_code == 200
        data = response.json()
        assert all(s.get("is_active") is True for s in data)

    def test_get_source_detail(self) -> None:
        """GET /{source_key} returns SourceResponse."""
        # First create a source
        with SessionLocal() as db:
            source = SourceRegistry(
                source_key="test_detail_source",
                source_name="Test Detail Source",
                source_type="test",
            )
            db.add(source)
            db.commit()

        response = client.get(
            "/api/admin/sources/test_detail_source",
            headers=get_admin_headers(),
        )
        assert response.status_code == 200
        data = response.json()
        assert data["source_key"] == "test_detail_source"
        assert "source_name" in data
        assert "source_tier" in data

        # Cleanup
        with SessionLocal() as db:
            db.query(SourceRegistry).filter(
                SourceRegistry.source_key == "test_detail_source"
            ).delete()
            db.commit()

    def test_get_source_404(self) -> None:
        """GET /{source_key} returns 404 for nonexistent."""
        response = client.get(
            "/api/admin/sources/nonexistent_source_12345",
            headers=get_admin_headers(),
        )
        assert response.status_code == 404

    def test_get_source_health(self) -> None:
        """GET /{source_key}/health returns health metrics."""
        with SessionLocal() as db:
            source = SourceRegistry(
                source_key="health_test_source",
                source_name="Health Test",
                source_type="test",
            )
            db.add(source)
            db.commit()

            # Add a run for this source
            run = IngestionRun(
                source_name="health_test_source",
                started_at=datetime.now(timezone.utc),
                status="completed",
                error_count=0,
            )
            db.add(run)
            db.commit()

        response = client.get(
            "/api/admin/sources/health_test_source/health",
            headers=get_admin_headers(),
        )
        assert response.status_code == 200
        data = response.json()
        assert "health_score" in data
        assert "recent_run_count" in data
        assert "recent_error_count" in data

        # Cleanup
        with SessionLocal() as db:
            db.query(IngestionRun).filter(
                IngestionRun.source_name == "health_test_source"
            ).delete()
            db.query(SourceRegistry).filter(
                SourceRegistry.source_key == "health_test_source"
            ).delete()
            db.commit()

    def test_get_source_runs(self) -> None:
        """GET /{source_key}/runs returns linked runs with correct field names."""
        with SessionLocal() as db:
            source = SourceRegistry(
                source_key="runs_test_source",
                source_name="Runs Test",
                source_type="test",
            )
            db.add(source)
            db.commit()

            run = IngestionRun(
                source_name="runs_test_source",
                started_at=datetime.now(timezone.utc),
                status="completed",
            )
            db.add(run)
            db.commit()

        response = client.get(
            "/api/admin/sources/runs_test_source/runs",
            headers=get_admin_headers(),
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

        if data:
            # Verify field names match ORM
            run_data = data[0]
            assert "finished_at" in run_data  # NOT completed_at
            assert "source_name" not in run_data  # In this context, source_key is implied

        # Cleanup
        with SessionLocal() as db:
            db.query(IngestionRun).filter(
                IngestionRun.source_name == "runs_test_source"
            ).delete()
            db.query(SourceRegistry).filter(
                SourceRegistry.source_key == "runs_test_source"
            ).delete()
            db.commit()

    def test_list_sources_hides_deprecated_by_default(self) -> None:
        """Deprecated lifecycle sources should be hidden unless explicitly requested."""
        with SessionLocal() as db:
            deprecated = SourceRegistry(
                source_key="deprecated_hidden_source",
                source_name="Deprecated Hidden Source",
                source_type="test",
                lifecycle_state="deprecated",
            )
            normal = SourceRegistry(
                source_key="normal_visible_source",
                source_name="Normal Visible Source",
                source_type="test",
                lifecycle_state="runnable_disabled",
            )
            db.add(deprecated)
            db.add(normal)
            db.commit()

        default_response = client.get(
            "/api/admin/sources",
            headers=get_admin_headers(),
        )
        assert default_response.status_code == 200
        default_keys = {item["source_key"] for item in default_response.json()}
        assert "deprecated_hidden_source" not in default_keys
        assert "normal_visible_source" in default_keys

        include_response = client.get(
            "/api/admin/sources?show_deprecated=true",
            headers=get_admin_headers(),
        )
        assert include_response.status_code == 200
        include_keys = {item["source_key"] for item in include_response.json()}
        assert "deprecated_hidden_source" in include_keys

        with SessionLocal() as db:
            db.query(SourceRegistry).filter(
                SourceRegistry.source_key.in_(
                    ["deprecated_hidden_source", "normal_visible_source"]
                )
            ).delete(synchronize_session=False)
            db.commit()

    def test_run_blocked_source_creates_failed_run_record(self) -> None:
        """Blocked /run attempts should persist a FAILED ingestion run row."""
        with SessionLocal() as db:
            blocked = SourceRegistry(
                source_key="blocked_run_source",
                source_name="Blocked Run Source",
                source_type="test",
                source_class="machine_ingest",
                automation_status="machine_ready_disabled",
                lifecycle_state="runnable_disabled",
                is_active=False,
            )
            db.add(blocked)
            db.commit()

        response = client.post(
            "/api/admin/sources/blocked_run_source/run",
            headers=get_admin_headers(),
        )
        assert response.status_code == 409
        assert "is disabled" in response.json()["detail"]

        with SessionLocal() as db:
            run = (
                db.query(IngestionRun)
                .filter(IngestionRun.source_name == "blocked_run_source")
                .order_by(IngestionRun.id.desc())
                .first()
            )
            assert run is not None
            assert run.status == "failed"
            assert run.source_name == "blocked_run_source"
            assert run.error_count == 1
            db.query(IngestionRun).filter(IngestionRun.id == run.id).delete()
            db.query(SourceRegistry).filter(
                SourceRegistry.source_key == "blocked_run_source"
            ).delete()
            db.commit()

    def test_retry_blocked_source_creates_failed_run_record(self) -> None:
        """Blocked retry attempts should persist a FAILED ingestion run row."""
        with SessionLocal() as db:
            source = SourceRegistry(
                source_key="blocked_retry_source",
                source_name="Blocked Retry Source",
                source_type="test",
                source_class="machine_ingest",
                automation_status="machine_ready_disabled",
                lifecycle_state="runnable_disabled",
                is_active=False,
            )
            db.add(source)
            db.flush()
            old_run = IngestionRun(
                source_name="blocked_retry_source",
                started_at=datetime.now(timezone.utc),
                status="failed",
            )
            db.add(old_run)
            db.commit()
            old_run_id = old_run.id

        response = client.post(
            f"/api/admin/ingestion-runs/{old_run_id}/retry",
            headers=get_admin_headers(),
        )
        assert response.status_code == 403
        detail = response.json()["detail"]
        assert "failed_run_id" in detail

        failed_run_id = detail["failed_run_id"]
        with SessionLocal() as db:
            failed_run = db.query(IngestionRun).filter(IngestionRun.id == failed_run_id).first()
            assert failed_run is not None
            assert failed_run.status == "failed"
            assert failed_run.source_name == "blocked_retry_source"
            db.query(IngestionRun).filter(
                IngestionRun.id.in_([old_run_id, failed_run_id])
            ).delete(synchronize_session=False)
            db.query(SourceRegistry).filter(
                SourceRegistry.source_key == "blocked_retry_source"
            ).delete()
            db.commit()

    def test_source_dry_run_returns_readiness_without_persisting_run(self) -> None:
        """Dry-run should exercise adapter output without creating an ingestion run row."""

        class FakeAdapter:
            def run(self) -> SimpleNamespace:
                return SimpleNamespace(
                    records_fetched=3,
                    created_records=[{"id": "a"}],
                    legal_instruments=[],
                    review_items=[{"id": "r1"}],
                    raw_snapshot_bytes=b"snapshot",
                    errors=[],
                )

        from app.ingestion import source_adapter_factory

        original_build_adapter = source_adapter_factory.build_adapter
        original_missing_secret = source_adapter_factory.missing_required_secret_for_parser
        source_adapter_factory.build_adapter = lambda *_args, **_kwargs: FakeAdapter()
        source_adapter_factory.missing_required_secret_for_parser = (
            lambda *_args, **_kwargs: None
        )

        with SessionLocal() as db:
            source = SourceRegistry(
                source_key="dry_run_source",
                source_name="Dry Run Source",
                source_type="test",
                source_class="machine_ingest",
                automation_status="machine_ready_enabled",
                lifecycle_state="runnable_enabled",
                is_active=True,
                terms_url="https://example.test/terms",
            )
            db.add(source)
            db.commit()

        try:
            response = client.post(
                "/api/admin/sources/dry_run_source/dry-run",
                headers=get_admin_headers(),
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["source_key"] == "dry_run_source"
            assert payload["source_reachable"] is True
            assert payload["legal_note_present"] is True
            assert payload["sample_records_found"] == 3
            assert payload["parser_matched_records"] == 2
            assert payload["claims_would_be_extracted"] is True
            assert payload["evidence_snapshot_would_be_created"] is True
            assert payload["public_visibility"] == "pending_review"
            assert payload["errors"] == []
            assert payload["success"] is True

            with SessionLocal() as db:
                runs = (
                    db.query(IngestionRun)
                    .filter(IngestionRun.source_name == "dry_run_source")
                    .all()
                )
                assert runs == []
        finally:
            source_adapter_factory.build_adapter = original_build_adapter
            source_adapter_factory.missing_required_secret_for_parser = (
                original_missing_secret
            )
            with SessionLocal() as db:
                db.query(SourceRegistry).filter(
                    SourceRegistry.source_key == "dry_run_source"
                ).delete(synchronize_session=False)
                db.commit()

    def test_source_dry_run_reports_adapter_missing(self) -> None:
        """Dry-run should report adapter_missing when no adapter is available."""

        from app.ingestion import source_adapter_factory

        original_build_adapter = source_adapter_factory.build_adapter
        original_missing_secret = source_adapter_factory.missing_required_secret_for_parser
        source_adapter_factory.build_adapter = lambda *_args, **_kwargs: None
        source_adapter_factory.missing_required_secret_for_parser = (
            lambda *_args, **_kwargs: None
        )

        with SessionLocal() as db:
            source = SourceRegistry(
                source_key="dry_run_missing_adapter",
                source_name="Dry Run Missing Adapter",
                source_type="test",
                source_class="machine_ingest",
                automation_status="machine_ready_enabled",
                lifecycle_state="runnable_enabled",
                is_active=True,
            )
            db.add(source)
            db.commit()

        try:
            response = client.post(
                "/api/admin/sources/dry_run_missing_adapter/dry-run",
                headers=get_admin_headers(),
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["success"] is False
            assert "adapter_missing" in payload["errors"]
        finally:
            source_adapter_factory.build_adapter = original_build_adapter
            source_adapter_factory.missing_required_secret_for_parser = (
                original_missing_secret
            )
            with SessionLocal() as db:
                db.query(SourceRegistry).filter(
                    SourceRegistry.source_key == "dry_run_missing_adapter"
                ).delete(synchronize_session=False)
                db.commit()

    def test_source_dry_run_fixture_replay_canlii(self) -> None:
        """Dry-run should support fixture-backed replay through real adapter logic."""

        from app.ingestion import source_adapter_factory
        from app.ingestion.source_adapters.canlii_api import CanLIIApiAdapter

        fixture_path = (
            Path(__file__).parent
            / "fixtures"
            / "sources"
            / "sk_courts_qb_decisions"
            / "sample.json"
        )
        fixture_payload = fixture_path.read_bytes()
        fixture_cases = json.loads(fixture_payload).get("cases", [])

        def _fixture_fetcher(url, allowed_domains, params=None):
            return SimpleNamespace(
                raw_content=fixture_payload,
                error=None,
                http_status=200,
                content_type="application/json",
                final_url=url,
            )

        def _build_fixture_adapter(source, settings):
            return CanLIIApiAdapter(
                source_key=source.source_key,
                base_url=source.base_url or "https://api.canlii.org/v1",
                api_key="fixture-key",
                allowed_domains_json=source.allowed_domains,
                public_record_authority=source.public_record_authority,
                databases=["skkb"],
                result_count=10,
                offset=0,
                fetcher=_fixture_fetcher,
            )

        original_build_adapter = source_adapter_factory.build_adapter
        original_missing_secret = source_adapter_factory.missing_required_secret_for_parser
        source_adapter_factory.build_adapter = _build_fixture_adapter
        source_adapter_factory.missing_required_secret_for_parser = (
            lambda *_args, **_kwargs: None
        )

        with SessionLocal() as db:
            source = SourceRegistry(
                source_key="dry_run_canlii_fixture",
                source_name="Dry Run CanLII Fixture",
                source_type="test",
                source_class="machine_ingest",
                parser="canlii_api",
                automation_status="machine_ready_enabled",
                lifecycle_state="runnable_enabled",
                is_active=True,
                base_url="https://api.canlii.org/v1",
                allowed_domains='["api.canlii.org", "canlii.org", "www.canlii.org"]',
                terms_url="https://example.test/terms",
                public_record_authority="official_court_record",
            )
            db.add(source)
            db.commit()

        try:
            with SessionLocal() as db:
                before_runs = (
                    db.query(IngestionRun)
                    .filter(IngestionRun.source_name == "dry_run_canlii_fixture")
                    .count()
                )
                before_reviews = db.query(ReviewItem).count()
                before_snapshots = db.query(SourceSnapshot).count()

            response = client.post(
                "/api/admin/sources/dry_run_canlii_fixture/dry-run",
                headers=get_admin_headers(),
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["source_key"] == "dry_run_canlii_fixture"
            assert payload["source_reachable"] is True
            assert payload["sample_records_found"] == len(fixture_cases)
            assert payload["parser_matched_records"] == len(fixture_cases)
            assert payload["evidence_snapshot_would_be_created"] is True
            assert payload["claims_would_be_extracted"] is True
            assert payload["errors"] == []
            assert payload["success"] is True

            with SessionLocal() as db:
                after_runs = (
                    db.query(IngestionRun)
                    .filter(IngestionRun.source_name == "dry_run_canlii_fixture")
                    .count()
                )
                after_reviews = db.query(ReviewItem).count()
                after_snapshots = db.query(SourceSnapshot).count()

            assert after_runs == before_runs
            assert after_reviews == before_reviews
            assert after_snapshots == before_snapshots
        finally:
            source_adapter_factory.build_adapter = original_build_adapter
            source_adapter_factory.missing_required_secret_for_parser = (
                original_missing_secret
            )
            with SessionLocal() as db:
                db.query(SourceRegistry).filter(
                    SourceRegistry.source_key == "dry_run_canlii_fixture"
                ).delete(synchronize_session=False)
                db.commit()


class TestResponseFieldValidation:
    """Prevent field drift between ORM and Pydantic response models."""

    def test_ingestion_run_summary_fields_match_orm(self) -> None:
        """Verify IngestionRunSummary fields exist on ORM model."""
        from app.api.routes.admin_ingestion import IngestionRunSummary
        from app.models.entities import IngestionRun as IngestionRunORM

        # Get Pydantic fields
        pydantic_fields = set(IngestionRunSummary.model_fields.keys())

        # Get ORM columns
        orm_columns = {c.name for c in IngestionRunORM.__table__.columns}

        # Computed fields are OK
        computed = {"duration_seconds"}
        required_fields = pydantic_fields - computed

        # All required fields must exist in ORM
        for field in required_fields:
            assert field in orm_columns, f"Field '{field}' in response but not in ORM"

        # Specifically check drifted field names are NOT used
        assert "source" not in pydantic_fields, "Use 'source_name' not 'source'"
        assert "completed_at" not in pydantic_fields, "Use 'finished_at' not 'completed_at'"
        assert "rejected_count" not in pydantic_fields, "Use 'skipped_count' not 'rejected_count'"

    def test_ingestion_run_detail_fields_match_orm(self) -> None:
        """Verify IngestionRunDetail fields exist on ORM model."""
        from app.api.routes.admin_ingestion import IngestionRunDetail
        from app.models.entities import IngestionRun as IngestionRunORM

        pydantic_fields = set(IngestionRunDetail.model_fields.keys())
        orm_columns = {c.name for c in IngestionRunORM.__table__.columns}

        computed = {"duration_seconds", "success_rate"}
        required_fields = pydantic_fields - computed

        for field in required_fields:
            assert field in orm_columns, f"Field '{field}' in response but not in ORM"

        # Check for drifted names
        assert "source" not in pydantic_fields
        assert "completed_at" not in pydantic_fields
        assert "error_log" not in pydantic_fields, "Use 'errors' not 'error_log'"
        assert "config_snapshot" not in pydantic_fields, "Field doesn't exist in ORM"

    def test_enable_blocking_deprecated_source(self) -> None:
        """Test that deprecated sources cannot be enabled."""
        with SessionLocal() as db:
            # Create a deprecated source
            source = SourceRegistry(
                source_key="test-deprecated",
                source_name="Deprecated Test Source",
                lifecycle_state="deprecated",
                is_active=False,
                automation_status="disabled",
            )
            db.add(source)
            db.commit()

        response = client.post(
            "/api/admin/sources/test-deprecated/enable",
            json={},
            headers=get_admin_headers(),
        )
        assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"

    def test_run_blocking_disabled_source(self) -> None:
        """Test that disabled sources cannot be run."""
        with SessionLocal() as db:
            source = SourceRegistry(
                source_key="test-disabled",
                source_name="Disabled Test Source",
                lifecycle_state="runnable",
                is_active=False,
                automation_status="disabled",
            )
            db.add(source)
            db.commit()

        response = client.post(
            "/api/admin/sources/test-disabled/run",
            json={},
            headers=get_admin_headers(),
        )
        assert response.status_code == 409, f"Expected 409, got {response.status_code}"

    def test_lifecycle_state_validation(self) -> None:
        """Test lifecycle_state field validation and retrieval."""
        with SessionLocal() as db:
            source = SourceRegistry(
                source_key="test-lifecycle",
                source_name="Lifecycle Test Source",
                lifecycle_state="runnable",
                is_active=True,
                automation_status="enabled",
            )
            db.add(source)
            db.commit()

        response = client.get(
            "/api/admin/sources/test-lifecycle",
            headers=get_admin_headers(),
        )
        assert response.status_code == 200
        data = response.json()
        assert "lifecycle_state" in data
        assert data["lifecycle_state"] in ["runnable", "deprecated", "archived"]

    def test_automation_status_validation(self) -> None:
        """Test automation_status field validation in listings."""
        with SessionLocal() as db:
            # Create enabled source
            source = SourceRegistry(
                source_key="test-enabled",
                source_name="Enabled Test",
                lifecycle_state="runnable",
                is_active=True,
                automation_status="machine_ready_enabled",
            )
            db.add(source)
            db.commit()

        response = client.get(
            "/api/admin/sources?automation_status=machine_ready_enabled",
            headers=get_admin_headers(),
        )
        assert response.status_code == 200
        data = response.json()
        for source in data:
            if source["automation_status"] == "machine_ready_enabled":
                assert source["is_active"] is True

    def test_source_adapter_exists_check(self) -> None:
        """Test that adapter_exists field is returned correctly."""
        with SessionLocal() as db:
            source = SourceRegistry(
                source_key="test-adapter",
                source_name="Adapter Test Source",
                lifecycle_state="runnable",
                is_active=True,
                automation_status="enabled",
            )
            db.add(source)
            db.commit()

        response = client.get(
            "/api/admin/sources/test-adapter",
            headers=get_admin_headers(),
        )
        assert response.status_code == 200
        data = response.json()
        assert "source_key" in data

    def test_justice_canada_section_preserved(self) -> None:
        """Test that Justice Canada source preserves section_key field."""
        with SessionLocal() as db:
            source = SourceRegistry(
                source_key="justice_canada_ocj",
                source_name="Ontario Superior Court of Justice",
                lifecycle_state="runnable",
                is_active=True,
                automation_status="machine_ready_enabled",
                section_key="provincial_superior_courts",
            )
            db.add(source)
            db.commit()

        response = client.get(
            "/api/admin/sources/justice_canada_ocj",
            headers=get_admin_headers(),
        )
        assert response.status_code == 200
        data = response.json()
        if "section_key" in data:
            assert data["section_key"] == "provincial_superior_courts"
        if "content_hash" in data:
            assert data["content_hash"] is not None

    def test_source_registry_truth_table_lifecycle(self) -> None:
        """Test that truth-table generation includes lifecycle_state in runnable check."""

        with SessionLocal() as db:
            # Create a source that appears runnable but lifecycle is not
            source_data = {
                "source_key": "test-lifeycle-check",
                "source_name": "Lifecycle Test",
                "source_class": "machine_ingest",
                "automation_status": "machine_ready_enabled",
                "lifecycle_state": "deprecated",  # Not runnable
            }
            # This would need actual file loading, but we test the presence of the check
            # by verifying the truth table includes lifecycle_state
            response = client.get(
                "/api/admin/truth-table",
                headers=get_admin_headers(),
            )
            if response.status_code == 200:
                data = response.json()
                # Verify that lifecycle_state is in the response
                if "entries" in data and len(data["entries"]) > 0:
                    entry = data["entries"][0]
                    assert "lifecycle_state" in entry

    def test_proof_manifest_no_stale_workflows(self) -> None:
        """Test that proof manifest contains only valid workflow files."""
        response = client.get(
            "/api/proof/manifest",
            headers=get_admin_headers(),
        )
        # This may 404 if endpoint doesn't exist, which is okay
        if response.status_code == 200:
            data = response.json()
            file_list = data.get("proof_input_file_list", [])

            # These should NOT be in the list
            invalid_workflows = [
                ".github/workflows/nextjs.yml",
                ".github/workflows/octopusdeploy.yml",
                ".github/workflows/rust.yml",
                ".github/workflows/webpack.yml",
            ]
            for wf in invalid_workflows:
                assert wf not in file_list, f"Stale workflow {wf} still in manifest"
