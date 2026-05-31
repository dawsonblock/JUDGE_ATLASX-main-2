"""Tests for production egress proxy enforcement in _validate_production_safety().

Phase 9 of enforcement plan: JTA_FETCH_EGRESS_PROXY must be set in production,
or JTA_ALLOW_DIRECT_PROD_FETCH_WITH_NETWORK_POLICY=1 must explicitly acknowledge
that a network-level policy enforces egress instead.
"""

from __future__ import annotations

import secrets
import types

import pytest

from app.main import _validate_production_safety


def _egress_safe_prod_settings(**overrides):
    """Return a Settings namespace that passes all pre-egress checks.

    Uses memory rate-limiting (avoids needing a live Redis) together with
    JTA_ALLOW_IN_MEMORY_RATE_LIMIT_PRODUCTION so the rate-limit guard
    does not exit before we reach the egress check.
    """
    defaults = dict(
        app_env="production",
        jwt_secret_key=secrets.token_hex(32),
        jwt_auth_enabled=True,
        enable_legacy_admin_token=False,
        rate_limit_backend="memory",
        redis_url="redis://localhost:6379/0",
        evidence_store_required=True,
        cors_origins="https://example.com",
        ingestion_queue_backend="inprocess",
    )
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


# ---------------------------------------------------------------------------
# Egress proxy tests
# ---------------------------------------------------------------------------


def test_egress_proxy_set_no_exit(monkeypatch):
    """When JTA_FETCH_EGRESS_PROXY is set, production start-up must succeed."""
    monkeypatch.setenv("JTA_ALLOW_IN_MEMORY_RATE_LIMIT_PRODUCTION", "1")
    monkeypatch.setenv("JTA_FETCH_EGRESS_PROXY", "http://squid-proxy:3128")
    monkeypatch.setenv("JTA_ALLOW_INPROCESS_QUEUE_PRODUCTION", "1")
    monkeypatch.delenv("JTA_ALLOW_DIRECT_PROD_FETCH_WITH_NETWORK_POLICY", raising=False)

    settings = _egress_safe_prod_settings()
    # Should complete without calling sys.exit
    _validate_production_safety(settings)


def test_no_egress_proxy_and_no_network_policy_override_exits(monkeypatch):
    """Missing proxy AND no network-policy override must cause sys.exit(1)."""
    monkeypatch.setenv("JTA_ALLOW_IN_MEMORY_RATE_LIMIT_PRODUCTION", "1")
    monkeypatch.setenv("JTA_ALLOW_INPROCESS_QUEUE_PRODUCTION", "1")
    monkeypatch.delenv("JTA_FETCH_EGRESS_PROXY", raising=False)
    monkeypatch.delenv("JTA_ALLOW_DIRECT_PROD_FETCH_WITH_NETWORK_POLICY", raising=False)

    settings = _egress_safe_prod_settings()
    with pytest.raises(SystemExit) as exc_info:
        _validate_production_safety(settings)
    assert exc_info.value.code == 1


def test_network_policy_escape_hatch_suppresses_exit(monkeypatch):
    """JTA_ALLOW_DIRECT_PROD_FETCH_WITH_NETWORK_POLICY=1 must suppress the exit
    even when JTA_FETCH_EGRESS_PROXY is absent."""
    monkeypatch.setenv("JTA_ALLOW_IN_MEMORY_RATE_LIMIT_PRODUCTION", "1")
    monkeypatch.setenv("JTA_ALLOW_INPROCESS_QUEUE_PRODUCTION", "1")
    monkeypatch.delenv("JTA_FETCH_EGRESS_PROXY", raising=False)
    monkeypatch.setenv("JTA_ALLOW_DIRECT_PROD_FETCH_WITH_NETWORK_POLICY", "1")

    settings = _egress_safe_prod_settings()
    # Should complete without calling sys.exit
    _validate_production_safety(settings)
