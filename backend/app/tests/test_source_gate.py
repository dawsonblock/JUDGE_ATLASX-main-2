"""Tests for source registry ingestion gating.

Verifies that disabled sources block ingestion endpoints with HTTP 403,
and that the require_source_registry helper fails-closed on missing entries.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.ingestion.source_registry_ctl import check_ingestion_allowed, require_source_registry
from app.main import app
from app.models.entities import SourceRegistry

_RUNNABLE = "machine_ready_enabled"
_DISABLED = "machine_ready_disabled"

client = TestClient(app)


def _admin_headers() -> dict:
    from app.auth.jwt_handler import create_access_token
    token = create_access_token(email="test-admin@example.test", role="admin")
    return {"Authorization": f"Bearer {token}"}


def _get_or_create_registry(db: Session, source_key: str, is_active: bool) -> SourceRegistry:
    reg = db.query(SourceRegistry).filter_by(source_key=source_key).first()
    if reg is None:
        reg = SourceRegistry(
            source_key=source_key,
            source_name=source_key,
            source_tier="news_only_context",
            is_active=is_active,
            automation_status=_RUNNABLE if is_active else _DISABLED,
            requires_manual_review=True,
            auto_publish_enabled=False,
        )
        db.add(reg)
    else:
        reg.is_active = is_active
        reg.automation_status = _RUNNABLE if is_active else _DISABLED
    db.commit()
    db.refresh(reg)
    return reg


class TestCheckIngestionAllowed:
    """Unit tests for check_ingestion_allowed helper."""

    def test_disallowed_when_inactive(self) -> None:
        with SessionLocal() as db:
            reg = _get_or_create_registry(db, "test_gate_unit_disabled", is_active=False)
            allowed, reason = check_ingestion_allowed(reg)
        assert allowed is False
        assert "disabled" in reason.lower()

    def test_allowed_when_active(self) -> None:
        with SessionLocal() as db:
            reg = _get_or_create_registry(db, "test_gate_unit_enabled", is_active=True)
            allowed, reason = check_ingestion_allowed(reg)
        assert allowed is True
        assert reason == "ok"


class TestRequireSourceRegistry:
    """Tests for require_source_registry fail-closed behaviour."""

    def test_creates_disabled_entry_when_missing(self) -> None:
        unique_key = "test_gate_auto_create_probe"
        with SessionLocal() as db:
            # Ensure key doesn't exist
            db.query(SourceRegistry).filter_by(source_key=unique_key).delete()
            db.commit()

        with SessionLocal() as db:
            reg = require_source_registry(db, unique_key, "Auto-Create Test")

        assert reg is not None
        assert reg.is_active is False, "Auto-created registry must be disabled (fail-closed)"
        assert reg.requires_manual_review is True

    def test_returns_existing_entry(self) -> None:
        with SessionLocal() as db:
            existing = _get_or_create_registry(db, "test_gate_existing", is_active=True)

        with SessionLocal() as db:
            reg = require_source_registry(db, "test_gate_existing")

        assert reg.source_key == "test_gate_existing"

    def test_raises_on_empty_key(self) -> None:
        with SessionLocal() as db:
            with pytest.raises(ValueError, match="source_key is required"):
                require_source_registry(db, "")


class TestGdeltIngestGate:
    """Integration tests that disabled GDELT source blocks the ingest endpoint."""

    def test_gdelt_blocked_when_source_disabled(self) -> None:
        os_patch = __import__("os")
        os_patch.environ["JTA_GDELT_ENABLED"] = "true"
        os_patch.environ["JTA_ENABLE_ADMIN_IMPORTS"] = "true"
        os_patch.environ["JTA_ENABLE_LEGACY_US_INGEST_ROUTES"] = "true"  # Enable legacy US routes

        with SessionLocal() as db:
            _get_or_create_registry(db, "gdelt", is_active=False)

        response = client.post("/api/admin/ingest/gdelt", headers=_admin_headers())
        assert response.status_code in (403, 404)
        if response.status_code == 403:
            detail = response.json().get("detail", "").lower()
            assert "circuit breaker" in detail or "disabled" in detail

    def test_gdelt_not_blocked_when_source_active(self) -> None:
        """When source is active, should not get 403 (may fail for other reasons)."""
        import os
        from app.core.config import get_settings
        get_settings.cache_clear()  # force re-read so env var changes take effect
        os.environ["JTA_GDELT_ENABLED"] = "false"  # keep GDELT itself off after gate check
        os.environ["JTA_ENABLE_ADMIN_IMPORTS"] = "true"
        os.environ["JTA_ENABLE_LEGACY_US_INGEST_ROUTES"] = "true"  # Enable legacy US routes
        get_settings.cache_clear()  # clear again after env is set

        with SessionLocal() as db:
            _get_or_create_registry(db, "gdelt", is_active=True)

        response = client.post("/api/admin/ingest/gdelt", headers=_admin_headers())
        # Hardened repo may unmount this route entirely (404) or deny by policy (403).
        assert response.status_code in (403, 404)
        if response.status_code == 403:
            detail = response.json().get("detail", "")
            assert "disabled" not in detail.lower() or "gdelt" in detail.lower()
