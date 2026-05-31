"""Source enablement gate regression tests.

These tests verify fail-closed behavior for source enablement and keep
publication state unchanged by enable/disable operations.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.api.routes.admin_sources import enable_source
from app.tests.test_source_run_policy import _make_db, _make_source


def _call_enable(source: object, *, missing_secret: str | None = None):
    import app.core.config as _config_mod

    db = _make_db(source)
    fake_factory = SimpleNamespace(
        build_adapter=MagicMock(return_value=MagicMock()),
        missing_required_secret_for_parser=MagicMock(return_value=missing_secret),
    )

    with (
        patch.object(_config_mod, "get_settings", return_value=MagicMock()),
        patch.dict(__import__("sys").modules, {"app.ingestion.source_adapter_factory": fake_factory}),
        patch("app.api.routes.admin_sources.log_mutation"),
    ):
        return enable_source(
            source_key=source.source_key,
            request=MagicMock(),
            db=db,
            actor=MagicMock(auth_method="jwt"),
        )


def test_portal_reference_cannot_be_enabled() -> None:
    src = _make_source(source_class="portal_reference", is_active=False)
    with pytest.raises(HTTPException) as exc_info:
        _call_enable(src)
    assert exc_info.value.status_code == 422


def test_disabled_stub_cannot_be_enabled() -> None:
    src = _make_source(source_class="disabled_stub", is_active=False)
    with pytest.raises(HTTPException) as exc_info:
        _call_enable(src)
    assert exc_info.value.status_code == 422


def test_adapter_missing_status_cannot_be_enabled() -> None:
    src = _make_source(source_class="machine_ingest", is_active=False)
    src.automation_status = "adapter_missing"
    with pytest.raises(HTTPException) as exc_info:
        _call_enable(src)
    assert exc_info.value.status_code == 422


def test_missing_secret_cannot_be_enabled() -> None:
    src = _make_source(source_class="machine_ingest", is_active=False, parser="canlii_api")
    with pytest.raises(HTTPException) as exc_info:
        _call_enable(src, missing_secret="JTA_CANLII_API_KEY")
    assert exc_info.value.status_code == 422


def test_valid_machine_ingest_source_can_be_enabled() -> None:
    src = _make_source(source_class="machine_ingest", is_active=False)
    result = _call_enable(src)
    assert result is src
    assert src.is_active is True


def test_enable_does_not_change_public_visibility_defaults() -> None:
    src = _make_source(source_class="machine_ingest", is_active=False)
    src.public_publish_default = False
    _call_enable(src)
    assert src.public_publish_default is False


def test_enable_does_not_auto_run_ingestion() -> None:
    src = _make_source(source_class="machine_ingest", is_active=False)
    db = _make_db(src)
    import app.core.config as _config_mod

    fake_factory = SimpleNamespace(
        build_adapter=MagicMock(return_value=MagicMock()),
        missing_required_secret_for_parser=MagicMock(return_value=None),
    )

    with (
        patch.object(_config_mod, "get_settings", return_value=MagicMock()),
        patch.dict(__import__("sys").modules, {"app.ingestion.source_adapter_factory": fake_factory}),
        patch("app.api.routes.admin_sources.log_mutation"),
    ):
        enable_source(
            source_key=src.source_key,
            request=MagicMock(),
            db=db,
            actor=MagicMock(auth_method="jwt"),
        )

    # Enable endpoint mutates SourceRegistry only; it should not enqueue or run ingestion.
    db.add.assert_not_called()
