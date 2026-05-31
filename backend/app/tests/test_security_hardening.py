"""Security hardening tests.

Covers:
1. JWT default-secret guard in _validate_production_safety()
2. CSV row-count hard cap via _check_csv_row_limit()
"""

from __future__ import annotations

import types

import pytest
from fastapi import HTTPException

from app.api.routes.admin_ingest import _check_csv_row_limit
from app.main import _validate_production_safety

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _prod_settings(**overrides):
    """Return a minimal namespace that looks like production Settings."""
    defaults = dict(
        app_env="production",
        jwt_secret_key="CHANGE-ME-BEFORE-PRODUCTION",
        jwt_auth_enabled=True,
        enable_legacy_admin_token=False,
        rate_limit_backend="redis",
        redis_url="redis://localhost:6379/0",
        evidence_store_required=False,
        cors_origins="https://example.com",
    )
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# Production safety: JWT secret guard
# ---------------------------------------------------------------------------


def test_default_jwt_secret_exits_in_production():
    """Default JWT secret must cause sys.exit(1) in production."""
    settings = _prod_settings(jwt_secret_key="CHANGE-ME-BEFORE-PRODUCTION")
    with pytest.raises(SystemExit) as exc_info:
        _validate_production_safety(settings)
    assert exc_info.value.code == 1


def test_custom_jwt_secret_does_not_exit():
    """A non-default JWT secret should not trigger the guard.

    We only assert the JWT check passes; other checks may still raise
    depending on environment, so we catch any *later* SystemExit.
    """
    import secrets

    strong_key = secrets.token_hex(32)
    settings = _prod_settings(jwt_secret_key=strong_key)
    # If the function reaches a *later* guard (Redis, admin tokens, etc.) that
    # is not what we are testing — the JWT check itself must not be the cause.
    # We verify by confirming the error message is NOT about JWT.
    exited = False
    captured_msg = ""
    import sys
    from unittest.mock import patch

    with patch("builtins.print") as mock_print, patch("sys.exit") as mock_exit:
        mock_exit.side_effect = SystemExit(1)
        try:
            _validate_production_safety(settings)
        except SystemExit:
            exited = True
            # Collect all printed messages
            calls = [str(c) for c in mock_print.call_args_list]
            captured_msg = " ".join(calls)

    # JWT error must NOT appear — if we exited for another reason that's fine
    assert "JTA_JWT_SECRET_KEY" not in captured_msg


def test_non_production_skips_all_checks():
    """Development / staging environments must bypass all safety checks."""
    # Even with the insecure default, no exit in non-production
    settings = _prod_settings(
        app_env="development",
        jwt_secret_key="CHANGE-ME-BEFORE-PRODUCTION",
        enable_legacy_admin_token=True,
    )
    # Should return normally — no SystemExit
    _validate_production_safety(settings)


def test_legacy_shared_token_auth_rejected_in_production():
    """Production startup must fail if legacy shared-token auth is enabled."""
    settings = _prod_settings(
        jwt_secret_key="strong-production-secret-value",
        enable_legacy_admin_token=True,
    )
    with pytest.raises(SystemExit) as exc_info:
        _validate_production_safety(settings)
    assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# CSV row-count hard cap
# ---------------------------------------------------------------------------


def _make_csv_bytes(rows: int) -> bytes:
    """Generate a minimal CSV with a header + `rows` data lines."""
    lines = [b"col_a,col_b,col_c"] + [b"a,b,c"] * rows
    return b"\n".join(lines)


def test_csv_row_limit_passes_under_cap():
    content = _make_csv_bytes(100)
    # Should not raise
    _check_csv_row_limit(content, 1000, "TestSource")


def test_csv_row_limit_passes_exactly_at_cap():
    content = _make_csv_bytes(1000)
    # Newline count == max_rows should still not raise
    _check_csv_row_limit(content, content.count(b"\n"), "TestSource")


def test_csv_row_limit_raises_over_cap():
    content = _make_csv_bytes(5001)
    with pytest.raises(HTTPException) as exc_info:
        _check_csv_row_limit(content, 5000, "TestSource")
    assert exc_info.value.status_code == 422


def test_csv_row_limit_error_includes_source_name():
    content = _make_csv_bytes(10_001)
    with pytest.raises(HTTPException) as exc_info:
        _check_csv_row_limit(content, 10_000, "Chicago")
    assert "Chicago" in exc_info.value.detail


def test_csv_row_limit_error_includes_counts():
    content = _make_csv_bytes(10_001)
    with pytest.raises(HTTPException) as exc_info:
        _check_csv_row_limit(content, 10_000, "Chicago")
    detail = exc_info.value.detail
    assert "10,000" in detail or "limit" in detail.lower()


def test_csv_empty_content_does_not_raise():
    _check_csv_row_limit(b"", 1_000_000, "TestSource")


def test_csv_header_only_does_not_raise():
    content = b"col_a,col_b\n"
    _check_csv_row_limit(content, 1_000_000, "TestSource")
