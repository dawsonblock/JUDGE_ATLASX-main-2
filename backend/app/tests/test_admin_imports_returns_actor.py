"""Proof tests: require_admin_imports returns AdminActor (not None).

These tests verify the core actor-returning contract of require_admin_imports
and require_import_actor, closing the architectural gap where the function
previously returned None and broke enforce_jwt_mutation_authority.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth.actor import AdminActor
from app.auth.admin import require_admin_imports
from app.auth.jwt_handler import create_access_token
from app.security.import_authority import require_import_actor


# ---------------------------------------------------------------------------
# Unit tests: require_import_actor returns AdminActor with correct fields
# ---------------------------------------------------------------------------

class TestRequireImportActorReturnsActor:
    """require_import_actor must return AdminActor — never None."""

    def _make_jwt_headers(self) -> dict:
        token = create_access_token(email="test-admin@example.test", role="admin")
        return {"Authorization": f"Bearer {token}"}

    def test_returns_adminactor_on_valid_jwt(self, monkeypatch):
        from unittest.mock import patch

        class FakeSettings:
            enable_admin_imports = True
            jwt_auth_enabled = True
            enable_legacy_admin_token = False
            enforce_jwt_mutations = True
            admin_token = None
            jwt_secret_key = "test-jwt-secret-key-for-tests-only"
            jwt_algorithm = "HS256"
            jwt_access_token_expire_minutes = 60

        import app.auth.admin as auth_admin
        monkeypatch.setattr(auth_admin, "get_settings", lambda: FakeSettings())

        token = create_access_token(email="actor-test@example.test", role="admin")
        actor = require_import_actor(
            x_jta_admin_token=None,
            authorization=f"Bearer {token}",
        )

        assert actor is not None, "require_import_actor must return AdminActor, not None"
        assert isinstance(actor, AdminActor), f"Expected AdminActor, got {type(actor)}"
        assert actor.auth_method == "jwt"
        assert actor.actor_type == "user"
        assert actor.email == "actor-test@example.test"

    def test_require_import_actor_enforces_source_admin_floor(self, monkeypatch):
        from fastapi import HTTPException
        import app.auth.admin as auth_admin

        class FakeSettings:
            enable_admin_imports = True
            jwt_auth_enabled = True
            enable_legacy_admin_token = False
            enforce_jwt_mutations = True

        monkeypatch.setattr(auth_admin, "get_settings", lambda: FakeSettings())

        token = create_access_token(email="viewer@example.test", role="viewer")
        with pytest.raises(HTTPException) as exc_info:
            require_import_actor(
                x_jta_admin_token=None,
                authorization=f"Bearer {token}",
            )

        assert exc_info.value.status_code == 403

    def test_require_import_actor_allows_source_admin(self, monkeypatch):
        import app.auth.admin as auth_admin

        class FakeSettings:
            enable_admin_imports = True
            jwt_auth_enabled = True
            enable_legacy_admin_token = False
            enforce_jwt_mutations = True

        monkeypatch.setattr(auth_admin, "get_settings", lambda: FakeSettings())

        token = create_access_token(email="source-admin@example.test", role="source_admin")
        actor = require_import_actor(
            x_jta_admin_token=None,
            authorization=f"Bearer {token}",
        )

        assert actor.role == "source_admin"
        assert actor.auth_method == "jwt"

    def test_disabled_imports_raises_403(self, monkeypatch):
        from fastapi import HTTPException
        import app.auth.admin as auth_admin

        class DisabledSettings:
            enable_admin_imports = False
            jwt_auth_enabled = True
            enable_legacy_admin_token = False

        monkeypatch.setattr(auth_admin, "get_settings", lambda: DisabledSettings())

        with pytest.raises(HTTPException) as exc_info:
            require_import_actor(x_jta_admin_token=None, authorization=None)
        assert exc_info.value.status_code == 403
        assert "disabled" in exc_info.value.detail.lower()
