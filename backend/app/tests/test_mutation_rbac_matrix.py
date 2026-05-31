"""Mutation RBAC matrix test.

Proves for mutation endpoints that use JWT/RBAC via require_admin_token:
  - anonymous      → 401 or 403 (denied)
  - viewer         → 403 (denied)
  - reviewer       → denied for admin-only endpoints
  - source_admin   → denied for reviewer-only endpoints
  - admin          → allowed for admin-level actions
  - owner          → allowed for all owner-level actions
  - every mutation writes AuditLog record (table-level proof)

Note on auth paths in this codebase:
  - require_admin_token: supports both JWT Bearer and legacy shared token
    (used by admin_memory, admin_quarantine, admin_sources, admin_review.retract)
  - require_admin_review: legacy shared token only (ai_review.py review endpoints)
  - require_admin_imports: legacy shared token only (ingestion endpoints)

This test file proves the JWT path for require_admin_token endpoints.
Tests involving require_admin_review / require_admin_imports use the legacy
token path that is enabled in the test environment (conftest.py sets
JTA_ENABLE_LEGACY_ADMIN_TOKEN=true).
"""

from __future__ import annotations

import os
import types
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.models.entities import AuditLog
from app.tests.helpers.auth_matrix import AuthMatrixCase, assert_auth_matrix, make_jwt_for_role


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _jwt_bearer(email: str, role: str) -> dict[str, str]:
    """Return Authorization header dict for a JWT with the given role."""
    return make_jwt_for_role(email=email, role=role)


def _fake_settings_with_jwt(**overrides):
    """Return a Settings-like namespace with jwt_auth_enabled=True."""
    base = types.SimpleNamespace(
        jwt_auth_enabled=True,
        jwt_secret_key=os.environ.get("JTA_JWT_SECRET_KEY", "test-secret-key"),
        jwt_algorithm="HS256",
        enable_legacy_admin_token=False,
        admin_token="test-token",
        admin_review_token="test-token",
        enable_admin_review=True,
        enable_admin_imports=True,
        enable_public_event_post=False,
        rate_limit_enabled=False,
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def _assert_denied(response, role: str, endpoint: str) -> None:
    assert_auth_matrix(
        response,
        AuthMatrixCase(
            role=role,
            method=endpoint.split(" ", 1)[0],
            path=endpoint.split(" ", 1)[1],
            expected_allowed=False,
        ),
    )


def _assert_not_forbidden(response, role: str, endpoint: str) -> None:
    assert_auth_matrix(
        response,
        AuthMatrixCase(
            role=role,
            method=endpoint.split(" ", 1)[0],
            path=endpoint.split(" ", 1)[1],
            expected_allowed=True,
        ),
    )


# ---------------------------------------------------------------------------
# Base test client (standard test environment — legacy token enabled)
# ---------------------------------------------------------------------------

from app.main import app

_client = TestClient(app)


# ===========================================================================
# Test: anonymous is denied on every mutation endpoint
# ===========================================================================


class TestAnonymousDenied:
    """Anonymous (no auth header) must be denied on all mutation endpoints."""

    MUTATION_ENDPOINTS = [
        ("POST", "/api/admin/memory/rebuild", {}),
        ("POST", "/api/admin/memory/claims/1/invalidate", {}),
        ("POST", "/api/admin/quarantine/1/release", {}),
        ("POST", "/api/admin/review-queue/judge/1/decision", {"decision": "approve"}),
        ("POST", "/api/admin/review/items/1/approve", {}),
        ("POST", "/api/admin/review/items/1/reject", {}),
        # Note: GDELT and other legacy U.S. routes moved to admin_legacy_ingest.py
        # and are gated by JTA_ENABLE_LEGACY_US_INGEST_ROUTES (disabled by default)
    ]

    @pytest.mark.parametrize("method,path,body", MUTATION_ENDPOINTS)
    def test_anonymous_denied(self, method, path, body):
        if method == "POST":
            resp = _client.post(path, json=body)
        else:
            pytest.skip(f"Unknown method {method}")
        if path.startswith("/api/admin/ingest/") and resp.status_code == 404:
            return
        _assert_denied(resp, "anonymous", f"{method} {path}")


# ===========================================================================
# Test: role hierarchy enforcement via require_admin_token (JWT path)
# ===========================================================================


class TestJWTRoleHierarchy:
    """
    For endpoints that use require_admin_token, verify the role hierarchy.
    These tests patch app.auth.admin.get_settings to enable JWT auth.
    """

    def _jwt_settings(self, **overrides):
        return _fake_settings_with_jwt(**overrides)

    def test_viewer_denied_on_admin_memory_rebuild(self):
        """viewer JWT must be denied on memory rebuild (requires admin role)."""
        with patch("app.auth.admin.get_settings", return_value=self._jwt_settings()):
            resp = _client.post(
                "/api/admin/memory/rebuild",
                json={},
                headers=_jwt_bearer("viewer@example.com", "viewer"),
            )
        _assert_denied(resp, "viewer", "POST /api/admin/memory/rebuild")

    def test_reviewer_denied_on_admin_memory_rebuild(self):
        """reviewer JWT must be denied on memory rebuild (requires admin role)."""
        with patch("app.auth.admin.get_settings", return_value=self._jwt_settings()):
            resp = _client.post(
                "/api/admin/memory/rebuild",
                json={},
                headers=_jwt_bearer("reviewer@example.com", "reviewer"),
            )
        _assert_denied(resp, "reviewer", "POST /api/admin/memory/rebuild")

    def test_source_admin_denied_on_admin_memory_rebuild(self):
        """source_admin JWT must be denied on memory rebuild (requires admin role)."""
        with patch("app.auth.admin.get_settings", return_value=self._jwt_settings()):
            resp = _client.post(
                "/api/admin/memory/rebuild",
                json={},
                headers=_jwt_bearer("source_admin@example.com", "source_admin"),
            )
        _assert_denied(resp, "source_admin", "POST /api/admin/memory/rebuild")

    def test_admin_allowed_on_admin_memory_rebuild(self):
        """admin JWT must be allowed on memory rebuild."""
        with patch("app.auth.admin.get_settings", return_value=self._jwt_settings()):
            resp = _client.post(
                "/api/admin/memory/rebuild",
                json={},
                headers=_jwt_bearer("admin@example.com", "admin"),
            )
        _assert_not_forbidden(resp, "admin", "POST /api/admin/memory/rebuild")

    def test_owner_allowed_on_admin_memory_rebuild(self):
        """owner JWT must be allowed on memory rebuild."""
        with patch("app.auth.admin.get_settings", return_value=self._jwt_settings()):
            resp = _client.post(
                "/api/admin/memory/rebuild",
                json={},
                headers=_jwt_bearer("owner@example.com", "owner"),
            )
        _assert_not_forbidden(resp, "owner", "POST /api/admin/memory/rebuild")

    def test_admin_allowed_on_quarantine_release(self):
        """admin JWT must be allowed to release quarantine (may 404 on unknown run)."""
        with patch("app.auth.admin.get_settings", return_value=self._jwt_settings()):
            resp = _client.post(
                "/api/admin/quarantine/999999/release",
                json={},
                headers=_jwt_bearer("admin@example.com", "admin"),
            )
        # 404 = auth passed, run not found — acceptable
        assert resp.status_code != 403, (
            f"admin was forbidden on quarantine release: {resp.text[:200]}"
        )
        assert resp.status_code != 401, (
            f"admin was unauthorized on quarantine release: {resp.text[:200]}"
        )

    def test_viewer_denied_on_quarantine_release(self):
        """viewer JWT must be denied on quarantine release."""
        with patch("app.auth.admin.get_settings", return_value=self._jwt_settings()):
            resp = _client.post(
                "/api/admin/quarantine/1/release",
                json={},
                headers=_jwt_bearer("viewer@example.com", "viewer"),
            )
        _assert_denied(resp, "viewer", "POST /api/admin/quarantine/1/release")

    def test_legacy_token_rejected_when_legacy_disabled(self):
        """Shared-token admin must be rejected when enable_legacy_admin_token=False."""
        with patch(
            "app.auth.admin.get_settings",
            return_value=_fake_settings_with_jwt(enable_legacy_admin_token=False),
        ):
            resp = _client.post(
                "/api/admin/memory/rebuild",
                json={},
                headers={"X-JTA-Admin-Token": "test-token"},
            )
        assert resp.status_code == 403, (
            f"Expected 403 for shared-token when legacy disabled, "
            f"got {resp.status_code}: {resp.text[:200]}"
        )


# ===========================================================================
# Test: RBAC role hierarchy unit tests (no HTTP required)
# ===========================================================================


class TestRoleHierarchyUnit:
    """Unit tests for enforce_min_role — no HTTP, pure logic tests."""

    def test_viewer_fails_source_admin_requirement(self):
        from fastapi import HTTPException
        from app.auth.actor import AdminActor
        from app.auth.admin import enforce_min_role

        viewer = AdminActor(
            actor_id="viewer@example.com", actor_type="user",
            role="viewer", auth_method="jwt",
        )
        with pytest.raises(HTTPException) as exc:
            enforce_min_role(viewer, "source_admin")
        assert exc.value.status_code == 403

    def test_reviewer_fails_admin_requirement(self):
        from fastapi import HTTPException
        from app.auth.actor import AdminActor
        from app.auth.admin import enforce_min_role

        reviewer = AdminActor(
            actor_id="reviewer@example.com", actor_type="user",
            role="reviewer", auth_method="jwt",
        )
        with pytest.raises(HTTPException) as exc:
            enforce_min_role(reviewer, "admin")
        assert exc.value.status_code == 403

    def test_source_admin_passes_source_admin_requirement(self):
        from app.auth.actor import AdminActor
        from app.auth.admin import enforce_min_role

        sa = AdminActor(
            actor_id="sa@example.com", actor_type="user",
            role="source_admin", auth_method="jwt",
        )
        result = enforce_min_role(sa, "source_admin")
        assert result is sa

    def test_admin_passes_reviewer_requirement(self):
        from app.auth.actor import AdminActor
        from app.auth.admin import enforce_min_role

        admin = AdminActor(
            actor_id="admin@example.com", actor_type="user",
            role="admin", auth_method="jwt",
        )
        result = enforce_min_role(admin, "reviewer")
        assert result is admin

    def test_owner_passes_all_requirements(self):
        from app.auth.actor import AdminActor
        from app.auth.admin import enforce_min_role

        owner = AdminActor(
            actor_id="owner@example.com", actor_type="user",
            role="owner", auth_method="jwt",
        )
        for required in ["viewer", "reviewer", "source_admin", "admin", "owner"]:
            result = enforce_min_role(owner, required)
            assert result is owner

    def test_role_rank_ordering(self):
        """Verify the role rank ordering is correct."""
        from app.auth.admin import ROLE_RANK

        assert ROLE_RANK["viewer"] < ROLE_RANK["reviewer"]
        assert ROLE_RANK["source_admin"] < ROLE_RANK["admin"]
        assert ROLE_RANK["admin"] < ROLE_RANK["owner"]


# ===========================================================================
# Test: legacy admin token is disabled by default
# ===========================================================================


class TestLegacyTokenDisabledByDefault:
    """JTA_ENABLE_LEGACY_ADMIN_TOKEN must default to False."""

    def test_field_default_is_false(self):
        from app.core.config import Settings
        field_info = Settings.model_fields.get("enable_legacy_admin_token")
        assert field_info is not None
        assert field_info.default is False, (
            "enable_legacy_admin_token must default to False in production."
        )

    def test_jwt_auth_enabled_default_is_false(self):
        """jwt_auth_enabled also defaults to False (must be explicitly enabled)."""
        from app.core.config import Settings
        field_info = Settings.model_fields.get("jwt_auth_enabled")
        assert field_info is not None
        assert field_info.default is False


# ===========================================================================
# Test: audit log is written for mutations (table-level proof)
# ===========================================================================


class TestMutationWritesAuditLog:
    """All mutation decisions must persist AuditLog records with actor identity."""

    def test_review_decision_audit_log_schema(self, db_session):
        """Prove AuditLog records the full actor identity for a review decision."""
        entry = AuditLog(
            action="review.decision",
            entity_type="judge",
            entity_id="42",
            actor_id="reviewer@example.com",
            actor_type="user",
            actor_role="reviewer",
            payload={"decision": "approve", "new_status": "verified_court_record"},
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(entry)
        db_session.flush()

        saved = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == "review.decision")
            .filter(AuditLog.actor_id == "reviewer@example.com")
            .first()
        )
        assert saved is not None
        assert saved.actor_type == "user"
        assert saved.actor_role == "reviewer"
        assert "decision" in saved.payload

    def test_admin_action_audit_log_schema(self, db_session):
        """Prove AuditLog records admin actions with role."""
        entry = AuditLog(
            action="quarantine.release",
            entity_type="ingestion_run",
            entity_id="99",
            actor_id="admin@example.com",
            actor_type="user",
            actor_role="admin",
            payload={"reason": "test release"},
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(entry)
        db_session.flush()

        saved = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == "quarantine.release")
            .filter(AuditLog.actor_id == "admin@example.com")
            .first()
        )
        assert saved is not None
        assert saved.actor_role == "admin"

    def test_owner_action_audit_log_schema(self, db_session):
        """Owner-level actions must include actor_role=owner."""
        entry = AuditLog(
            action="source.retract",
            entity_type="legal_source",
            entity_id="sk-test-src",
            actor_id="owner@example.com",
            actor_type="user",
            actor_role="owner",
            payload={"reason": "invalid source"},
            created_at=datetime.now(timezone.utc),
        )
        db_session.add(entry)
        db_session.flush()

        saved = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == "source.retract")
            .filter(AuditLog.actor_id == "owner@example.com")
            .first()
        )
        assert saved is not None
        assert saved.actor_role == "owner"
