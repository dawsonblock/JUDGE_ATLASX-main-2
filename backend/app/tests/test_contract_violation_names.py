"""Tests for canonical contract-violation names.

These guards keep the public vocabulary stable: `no_fetch_url` is canonical and
`no_source_url` must not be emitted by current validation or admin run results.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.ingestion.adapters import IngestionResult
from app.ingestion.source_runner import _validate_machine_ingest_contract
from app.models.entities import SourceRegistry


def _make_source(*, base_url: str | None = None) -> SourceRegistry:
    source = SourceRegistry(source_key="test_source", source_name="Test Source")
    source.base_url = base_url
    source.parser_version = "1.0"
    source.source_class = "machine_ingest"
    source.lifecycle_state = "runnable"
    source.allowed_domains = '["example.com"]'
    source.requires_manual_review = True
    source.public_publish_default = False
    source.parser = "laws_justice_xml"
    source.source_key = "test_source"
    return source


def _make_result(*, fetch_url: str | None = None) -> IngestionResult:
    return IngestionResult(
        source_key="test_source",
        raw_snapshot_bytes=b"content",
        fetch_url=fetch_url,
        fetch_http_status=200,
        fetch_content_type="text/html",
        parser_version="1.0",
        created_records=[],
        review_items=[],
        errors=[],
    )


def test_missing_fetch_url_uses_canonical_name() -> None:
    violations = _validate_machine_ingest_contract(_make_result(fetch_url=None), _make_source())
    assert "no_fetch_url" in violations
    assert "no_source_url" not in violations


def test_admin_run_response_uses_canonical_violation_names() -> None:
    from app.api.routes.admin_sources import run_source_now

    source = _make_source(base_url="https://example.com/feed")
    source.is_active = True
    source.automation_status = "machine_ready_enabled"

    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = source

    run = MagicMock()
    run.id = 99
    run.status = "running"
    run.persisted_count = 0
    run.skipped_count = 0
    run.error_count = 0
    run.errors = []
    run.pipeline_stage = "adapter.run"

    result = _make_result(fetch_url=None)
    result.created_records = []
    result.review_items = []

    with patch("app.core.config.get_settings", return_value=MagicMock()):
        with patch("app.ingestion.source_adapter_factory.build_adapter") as build_adapter:
            adapter = MagicMock()
            adapter.run.return_value = result
            build_adapter.return_value = adapter
            with patch("app.ingestion.source_runner.persist_ingestion_result") as persist:
                persist.return_value = SimpleNamespace(
                    persisted_incidents=0,
                    skipped_duplicates=0,
                    persisted_review_items=0,
                    snapshots_written=1,
                    quarantined_count=1,
                    failed_records=0,
                    review_items_skipped=0,
                    contract_violations=["no_fetch_url"],
                    warnings=[],
                )
                with patch("app.api.routes.admin_sources.update_source_health"), patch("app.api.routes.admin_sources.log_mutation"):
                    response = run_source_now(
                        source_key="test_source",
                        request=MagicMock(),
                        run_mode="synchronous",
                        db=db,
                        actor=MagicMock(auth_method="jwt"),
                    )

    assert response["contract_violations"] == ["no_fetch_url"]
    assert "no_source_url" not in response["contract_violations"]
