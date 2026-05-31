"""Tests for the source-run access policy in admin_sources.run_source_now.

Verifies that:
- Only machine_ingest sources can be launched; every other source_class returns 422.
- A machine_ingest source that has no registered adapter returns 501.
- An inactive source returns 409 before any class check.
- A missing source returns 404.
- A successful adapter run records an IngestionRun with status=completed.
- An adapter exception still flushes an IngestionRun with status=failed.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.models.entities import SourceRegistry

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source(
    source_key: str = "test_src",
    is_active: bool = True,
    source_class: str | None = "machine_ingest",
    parser: str | None = None,
) -> SourceRegistry:
    if parser is None:
        from app.ingestion.source_adapters import ADAPTER_REGISTRY

        parser = next(iter(ADAPTER_REGISTRY.keys()))

    src = SourceRegistry(
        source_key=source_key,
        source_name=f"Source {source_key}",
    )
    src.source_key = source_key
    src.is_active = is_active
    src.source_class = source_class
    src.lifecycle_state = "runnable" if is_active else "runnable_disabled"
    src.parser = parser
    src.parser_version = "1.0"
    src.allowed_domains = '["example.com"]'
    src.base_url = "https://example.com/feed"
    src.public_record_authority = "official_public_record"
    src.terms_url = "https://example.com/terms"
    src.requires_manual_review = True
    src.public_publish_default = False
    src.automation_status = "machine_ready_disabled"
    return src


def _make_db(source: object | None) -> MagicMock:
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = source
    return db


def _make_adapter_result(success: bool = True) -> SimpleNamespace:
    return SimpleNamespace(
        records_fetched=5,
        records_skipped=0,
        created_records=[],
        review_items=[],
        errors=[],
        success=success,
    )


def _run(source: object | None, adapter=None, adapter_error: Exception | None = None):
    """Call run_source_now with a fully mocked context."""
    import sys
    import types

    import app.core.config as _config_mod
    import app.ingestion.source_runner as _runner_mod
    from app.api.routes.admin_sources import run_source_now

    db = _make_db(source)
    request = MagicMock()
    actor = MagicMock()
    actor.auth_method = "jwt"  # satisfy enforce_jwt_mutation_authority

    # source_adapter_factory pulls in bs4 transitively and cannot be directly
    # imported in the test environment.  We inject a stub into sys.modules so
    # the local `from ... import build_adapter` inside run_source_now picks up
    # our mock without triggering the real import chain.
    _fake_factory = types.SimpleNamespace(
        build_adapter=MagicMock(return_value=adapter),
        missing_required_secret_for_parser=MagicMock(return_value=None),
    )

    with (
        patch.object(_config_mod, "get_settings", return_value=MagicMock()),
        patch.dict(sys.modules, {"app.ingestion.source_adapter_factory": _fake_factory}),
        patch.object(
            _runner_mod,
            "persist_ingestion_result",
            return_value=MagicMock(
                persisted_incidents=0, skipped_duplicates=0, persisted_review_items=0
            ),
        ),
        patch("app.api.routes.admin_sources.update_source_health"),
        patch("app.api.routes.admin_sources.log_mutation"),
    ):
        if adapter is not None and adapter_error:
            adapter.run.side_effect = adapter_error
        elif adapter is not None:
            adapter.run.return_value = _make_adapter_result()

        return run_source_now(
            source_key=source.source_key if source else "missing",
            request=request,
            run_mode="synchronous",
            db=db,
            actor=actor,
        )


# ---------------------------------------------------------------------------
# 404 — missing source
# ---------------------------------------------------------------------------


class TestRunSourceMissing:
    def test_missing_source_returns_404(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            _run(source=None)
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# 409 — inactive source
# ---------------------------------------------------------------------------


class TestRunSourceInactive:
    def test_inactive_source_returns_409(self) -> None:
        src = _make_source(is_active=False, source_class="machine_ingest")
        with pytest.raises(HTTPException) as exc_info:
            _run(src)
        assert exc_info.value.status_code == 409


# ---------------------------------------------------------------------------
# 422 — non-runnable source_class
# ---------------------------------------------------------------------------


class TestRunSourceClassPolicy:
    @pytest.mark.parametrize(
        "sc",
        [
            "portal_reference",
            "manual_reference",
            "requires_api_key",
            "disabled_stub",
            "needs_endpoint_configuration",
            None,
        ],
    )
    def test_non_machine_ingest_returns_422(self, sc: str | None) -> None:
        src = _make_source(source_class=sc)
        with pytest.raises(HTTPException) as exc_info:
            _run(src)
        exc = exc_info.value
        assert exc.status_code == 422
        assert isinstance(exc.detail, dict)
        assert exc.detail["source_class"] == sc
        assert "next_action" in exc.detail

    def test_machine_ingest_is_allowed_with_adapter(self) -> None:
        src = _make_source(source_class="machine_ingest")
        src.automation_status = "machine_ready_enabled"
        adapter = MagicMock()
        adapter.run.return_value = _make_adapter_result()
        result = _run(src, adapter=adapter)
        assert result["success"] is True

    def test_422_detail_contains_source_key(self) -> None:
        src = _make_source(source_class="portal_reference", source_key="spd_portal")
        with pytest.raises(HTTPException) as exc_info:
            _run(src)
        assert exc_info.value.detail["source_key"] == "spd_portal"


# ---------------------------------------------------------------------------
# 501 — no adapter registered
# ---------------------------------------------------------------------------


class TestRunSourceNoAdapter:
    def test_nil_adapter_returns_501(self) -> None:
        src = _make_source(source_class="machine_ingest")
        src.automation_status = "machine_ready_enabled"
        with pytest.raises(HTTPException) as exc_info:
            _run(src, adapter=None)
        assert exc_info.value.status_code == 501

    def test_missing_canlii_secret_returns_422(self) -> None:
        import sys
        import types

        import app.core.config as _config_mod
        from app.api.routes.admin_sources import run_source_now

        src = _make_source(source_class="machine_ingest", parser="canlii_api")
        src.automation_status = "machine_ready_enabled"
        db = _make_db(src)
        _fake_factory = types.SimpleNamespace(
            build_adapter=MagicMock(return_value=MagicMock()),
            missing_required_secret_for_parser=MagicMock(return_value="JTA_CANLII_API_KEY"),
        )

        with (
            patch.object(
                _config_mod,
                "get_settings",
                return_value=MagicMock(canlii_api_key=None, lexum_api_key=None),
            ),
            patch.dict(sys.modules, {"app.ingestion.source_adapter_factory": _fake_factory}),
        ):
            with pytest.raises(HTTPException) as exc_info:
                run_source_now(
                    source_key=src.source_key,
                    request=MagicMock(),
                    run_mode="synchronous",
                    db=db,
                    actor=MagicMock(auth_method="jwt"),
                )

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["missing_secret"] == "JTA_CANLII_API_KEY"


# ---------------------------------------------------------------------------
# 500 — adapter raises
# ---------------------------------------------------------------------------


class TestRunSourceAdapterError:
    def test_adapter_exception_returns_500(self) -> None:
        src = _make_source(source_class="machine_ingest")
        src.automation_status = "machine_ready_enabled"
        adapter = MagicMock()
        with pytest.raises(HTTPException) as exc_info:
            _run(src, adapter=adapter, adapter_error=RuntimeError("timeout"))
        assert exc_info.value.status_code == 500

    def test_adapter_exception_records_failed_run(self) -> None:
        """update_source_health must still be called even when the adapter crashes."""
        import sys
        import types

        import app.core.config as _config_mod
        import app.ingestion.source_runner as _runner_mod

        src = _make_source(source_class="machine_ingest")
        src.automation_status = "machine_ready_enabled"
        adapter = MagicMock()
        _fake_factory = types.SimpleNamespace(
            build_adapter=MagicMock(return_value=adapter),
            missing_required_secret_for_parser=MagicMock(return_value=None),
        )

        with (
            patch.object(_config_mod, "get_settings", return_value=MagicMock()),
            patch.dict(sys.modules, {"app.ingestion.source_adapter_factory": _fake_factory}),
            patch.object(_runner_mod, "persist_ingestion_result"),
            patch("app.api.routes.admin_sources.update_source_health") as mock_health,
            patch("app.api.routes.admin_sources.log_mutation"),
        ):
            adapter.run.side_effect = RuntimeError("network error")
            db = _make_db(src)

            from app.api.routes.admin_sources import run_source_now

            with pytest.raises(HTTPException):
                run_source_now(
                    source_key=src.source_key,
                    request=MagicMock(),
                    run_mode="synchronous",
                    db=db,
                    actor=MagicMock(auth_method="jwt"),
                )

            mock_health.assert_called_once()
            assert db.rollback.call_count == 1
            assert db.commit.call_count == 2
            db.merge.assert_called_once()


# ---------------------------------------------------------------------------
# enable_source — source_class guard (Phase 4)
# ---------------------------------------------------------------------------


def _enable(source: object | None):
    """Call enable_source with a fully mocked context."""
    import sys
    import types

    import app.core.config as _config_mod
    from app.api.routes.admin_sources import enable_source

    db = _make_db(source)
    _fake_factory = types.SimpleNamespace(
        build_adapter=MagicMock(return_value=MagicMock()),
        missing_required_secret_for_parser=MagicMock(return_value=None),
    )

    with (
        patch.object(_config_mod, "get_settings", return_value=MagicMock()),
        patch.dict(sys.modules, {"app.ingestion.source_adapter_factory": _fake_factory}),
        patch("app.api.routes.admin_sources.log_mutation"),
    ):
        return enable_source(
            source_key=source.source_key if source else "missing",
            request=MagicMock(),
            db=db,
            actor=MagicMock(auth_method="jwt"),
        )


class TestEnableSourceClassPolicy:
    def test_missing_source_returns_404(self) -> None:
        with pytest.raises(HTTPException) as exc_info:
            _enable(source=None)
        assert exc_info.value.status_code == 404

    @pytest.mark.parametrize(
        "sc",
        [
            "portal_reference",
            "manual_reference",
            "requires_api_key",
            "disabled_stub",
            "needs_endpoint_configuration",
            None,
        ],
    )
    def test_non_machine_ingest_enable_returns_422(self, sc: str | None) -> None:
        src = _make_source(source_class=sc, is_active=False)
        with pytest.raises(HTTPException) as exc_info:
            _enable(src)
        assert exc_info.value.status_code == 422

    def test_machine_ingest_enable_succeeds(self) -> None:
        src = _make_source(source_class="machine_ingest", is_active=False)
        with patch("app.api.routes.admin_sources.log_mutation"):
            result = _enable(src)
        assert result is src
        assert src.is_active is True

    def test_enable_requires_canlii_secret(self) -> None:
        import sys
        import types

        import app.core.config as _config_mod
        from app.api.routes.admin_sources import enable_source

        src = _make_source(source_class="machine_ingest", is_active=False, parser="canlii_api")
        db = _make_db(src)
        _fake_factory = types.SimpleNamespace(
            build_adapter=MagicMock(return_value=MagicMock()),
            missing_required_secret_for_parser=MagicMock(return_value="JTA_CANLII_API_KEY"),
        )

        with (
            patch.object(
                _config_mod,
                "get_settings",
                return_value=MagicMock(canlii_api_key=None, lexum_api_key=None),
            ),
            patch.dict(sys.modules, {"app.ingestion.source_adapter_factory": _fake_factory}),
            patch("app.api.routes.admin_sources.log_mutation"),
        ):
            with pytest.raises(HTTPException) as exc_info:
                enable_source(
                    source_key=src.source_key,
                    request=MagicMock(),
                    db=db,
                    actor=MagicMock(auth_method="jwt"),
                )

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["missing_secret"] == "JTA_CANLII_API_KEY"

    def test_enable_fails_closed_when_audit_write_fails(self) -> None:
        """Critical mutation must rollback when audit append fails."""
        import sys
        import types

        import app.core.config as _config_mod
        from app.api.routes.admin_sources import enable_source

        src = _make_source(source_class="machine_ingest", is_active=False)
        db = _make_db(src)
        _fake_factory = types.SimpleNamespace(
            build_adapter=MagicMock(return_value=MagicMock()),
            missing_required_secret_for_parser=MagicMock(return_value=None),
        )

        with (
            patch.object(_config_mod, "get_settings", return_value=MagicMock()),
            patch.dict(sys.modules, {"app.ingestion.source_adapter_factory": _fake_factory}),
            patch("app.api.routes.admin_sources.log_mutation", side_effect=RuntimeError("audit down")),
        ):
            with pytest.raises(HTTPException) as exc_info:
                enable_source(
                    source_key=src.source_key,
                    request=MagicMock(),
                    db=db,
                    actor=MagicMock(auth_method="jwt"),
                )

        assert exc_info.value.status_code == 500
        db.rollback.assert_called_once()
        db.commit.assert_not_called()


# ---------------------------------------------------------------------------
# update_source PATCH — is_active=True guard (Phase 4)
# ---------------------------------------------------------------------------


def _patch_source(source: object | None, **kwargs):
    """Call update_source with a mocked context."""
    from app.api.routes.admin_sources import update_source, SourceUpdateRequest

    db = _make_db(source)
    update = SourceUpdateRequest(**kwargs)
    with patch("app.api.routes.admin_sources.log_mutation"):
        return update_source(
            source_key=source.source_key if source else "missing",
            update=update,
            request=MagicMock(),
            db=db,
            actor=MagicMock(auth_method="jwt"),
        )


class TestUpdateSourceClassPolicy:
    @pytest.mark.parametrize(
        "sc",
        [
            "portal_reference",
            "manual_reference",
            "requires_api_key",
            "disabled_stub",
            "needs_endpoint_configuration",
            None,
        ],
    )
    def test_activate_non_machine_ingest_returns_422(self, sc: str | None) -> None:
        src = _make_source(source_class=sc, is_active=False)
        with pytest.raises(HTTPException) as exc_info:
            _patch_source(src, is_active=True)
        assert exc_info.value.status_code == 422

    def test_patch_disallow_is_active_false(self) -> None:
        """PATCH must reject activation changes; use /enable or /disable endpoints."""
        src = _make_source(source_class="portal_reference", is_active=True)
        with pytest.raises(HTTPException) as exc_info:
            _patch_source(src, is_active=False)
        assert exc_info.value.status_code == 422

    def test_patch_disallow_is_active_true(self) -> None:
        src = _make_source(source_class="machine_ingest", is_active=False)
        with pytest.raises(HTTPException) as exc_info:
            _patch_source(src, is_active=True)
        assert exc_info.value.status_code == 422

    def test_patch_notes_on_non_machine_ingest_allowed(self) -> None:
        """Non-activation patches (e.g. admin_notes) must still work on any class."""
        src = _make_source(source_class="portal_reference")
        result = _patch_source(src, admin_notes="Updated manually")
        assert result is src

    def test_update_fails_closed_when_audit_write_fails(self) -> None:
        """PATCH source must not commit when audit append fails."""
        from app.api.routes.admin_sources import SourceUpdateRequest, update_source

        src = _make_source(source_class="machine_ingest", is_active=False)
        db = _make_db(src)

        with patch("app.api.routes.admin_sources.log_mutation", side_effect=RuntimeError("audit down")):
            with pytest.raises(HTTPException) as exc_info:
                update_source(
                    source_key=src.source_key,
                    update=SourceUpdateRequest(admin_notes="audit-tripwire"),
                    request=MagicMock(),
                    db=db,
                    actor=MagicMock(auth_method="jwt"),
                )

        assert exc_info.value.status_code == 500
        db.rollback.assert_called_once()
        db.commit.assert_not_called()
