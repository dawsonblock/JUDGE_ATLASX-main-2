"""Test that SourceRegistry control plane blocks disabled sources."""
import pytest
from datetime import datetime, timezone
from app.models.entities import SourceRegistry, IngestionRun
from app.ingestion.source_registry_ctl import (
    check_ingestion_allowed,
    require_source_registry,
    update_source_health,
)


def test_disabled_source_blocks_ingestion(db_session):
    """Disabled source must fail ingestion with clear error."""
    source = SourceRegistry(
        source_key="test_disabled_source",
        source_name="Test Disabled Source",
        source_type="test",
        country="US",
        source_tier="news_only_context",
        is_active=False,  # DISABLED
        automation_status="machine_ready_disabled",
        health_score=1.0,
    )
    db_session.add(source)
    db_session.commit()

    # Check if ingestion is allowed
    allowed, reason = check_ingestion_allowed(source)
    assert not allowed, "Disabled source must block ingestion"
    assert "disabled" in reason.lower(), "Error message should mention disabled status"


def test_missing_source_auto_creates_disabled(db_session):
    """Attempting to ingest from missing source auto-creates disabled registry."""
    source = require_source_registry(
        db_session,
        source_key="test_new_source",
        source_name="New Test Source",
    )
    assert source.is_active is False, "New source registry entries must be disabled by default"
    assert source.source_key == "test_new_source"
    
    # Verify ingestion is blocked
    allowed, reason = check_ingestion_allowed(source)
    assert not allowed, "New (disabled) source must block ingestion"


def test_enabled_source_allows_ingestion(db_session):
    """Enabled source must allow ingestion."""
    source = SourceRegistry(
        source_key="test_enabled_source",
        source_name="Test Enabled Source",
        source_type="test",
        country="US",
        source_tier="official_police_open_data",
        is_active=True,  # ENABLED
        automation_status="machine_ready_enabled",
        health_score=0.95,
    )
    db_session.add(source)
    db_session.commit()

    # Check if ingestion is allowed
    allowed, reason = check_ingestion_allowed(source)
    assert allowed, "Enabled source must allow ingestion"


def test_admin_enable_flips_is_active_true(db_session):
    """Simulate admin enabling a source."""
    source = SourceRegistry(
        source_key="test_enable_source",
        source_name="Test Enable Source",
        source_type="test",
        country="US",
        source_tier="news_only_context",
        is_active=False,
        automation_status="machine_ready_disabled",
    )
    db_session.add(source)
    db_session.commit()

    # Admin enables
    source.is_active = True
    source.automation_status = "machine_ready_enabled"
    source.updated_at = datetime.now(timezone.utc)
    db_session.commit()

    # Verify ingestion now allowed
    allowed, reason = check_ingestion_allowed(source)
    assert allowed, "Re-enabled source must allow ingestion"
    assert source.is_active is True


def test_admin_disable_flips_is_active_false(db_session):
    """Simulate admin disabling a source."""
    source = SourceRegistry(
        source_key="test_disable_source",
        source_name="Test Disable Source",
        source_type="test",
        country="US",
        source_tier="official_police_open_data",
        is_active=True,
        automation_status="machine_ready_enabled",
    )
    db_session.add(source)
    db_session.commit()

    # Admin disables
    source.is_active = False
    source.automation_status = "machine_ready_disabled"
    source.updated_at = datetime.now(timezone.utc)
    db_session.commit()

    # Verify ingestion blocked
    allowed, reason = check_ingestion_allowed(source)
    assert not allowed, "Disabled source must block ingestion"
    assert source.is_active is False


def test_ingestion_run_fails_if_source_disabled(db_session):
    """Ingestion runner must fail closed if source is disabled."""
    source = SourceRegistry(
        source_key="test_run_disabled",
        source_name="Test Run Disabled",
        source_type="test",
        country="US",
        source_tier="news_only_context",
        is_active=False,
        automation_status="machine_ready_disabled",
    )
    db_session.add(source)
    db_session.commit()

    # Simulate ingestion check
    allowed, reason = check_ingestion_allowed(source)
    
    if not allowed:
        # Create failed run
        run = IngestionRun(
            source_name=source.source_key,
            started_at=datetime.now(timezone.utc),
            status="failed",
            errors=[reason],
            error_count=1,
            fetched_count=0,
            parsed_count=0,
            persisted_count=0,
            finished_at=datetime.now(timezone.utc),
        )
        db_session.add(run)
        db_session.commit()

    # Verify run was created with failure
    run = db_session.query(IngestionRun).filter_by(source_name="test_run_disabled").first()
    assert run is not None, "Run should be created"
    assert run.status == "failed", "Run must be marked failed"
    assert "disabled" in run.errors[0].lower(), "Error must mention disabled status"


def test_source_registry_is_only_runtime_switch(db_session):
    """Verify SourceRegistry.is_active is the only runtime ingestion authority."""
    source = SourceRegistry(
        source_key="test_authority",
        source_name="Test Authority",
        source_type="test",
        country="US",
        source_tier="news_only_context",
        is_active=True,
        automation_status="machine_ready_enabled",
    )
    db_session.add(source)
    db_session.commit()

    # Even if other conditions might suggest enabling, is_active is the authority
    allowed, _ = check_ingestion_allowed(source)
    assert allowed, "is_active=True must allow"

    # Disable it
    source.is_active = False
    source.automation_status = "machine_ready_disabled"
    db_session.commit()

    allowed, _ = check_ingestion_allowed(source)
    assert not allowed, "is_active=False must block, regardless of other factors"

    # Re-enable
    source.is_active = True
    source.automation_status = "machine_ready_enabled"
    db_session.commit()

    allowed, _ = check_ingestion_allowed(source)
    assert allowed, "is_active=True must allow again"


def test_runner_blocks_when_source_disabled(db_session):
    """run_courtlistener_ingestion must fail closed when source is disabled.

    require_source_registry auto-creates a disabled entry for unknown source keys,
    so calling the runner against a clean DB must return a failed IngestionRun
    without ever invoking the external adapter.
    """
    from app.ingestion.runner import run_courtlistener_ingestion

    # Use a unique source key so require_source_registry auto-creates a disabled entry.
    # We patch the runner's registry lookup by pre-inserting a disabled "courtlistener" row.
    registry = require_source_registry(
        db_session,
        source_key="courtlistener",
        source_name="CourtListener API",
    )
    # Explicitly disable in case a prior test activated it in the shared SQLite DB.
    registry.is_active = False
    db_session.commit()

    since = datetime(2020, 1, 1, tzinfo=timezone.utc)
    run = run_courtlistener_ingestion(db_session, since)

    assert run.status == "failed", "Runner must return failed status when source disabled"
    assert run.error_count >= 1, "Runner must record at least one error"
    assert any("blocked" in (e or "").lower() for e in (run.errors or [])), (
        "Error message must mention 'blocked'"
    )
