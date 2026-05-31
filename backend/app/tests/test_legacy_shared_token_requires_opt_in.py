"""Proof that shared-token import access requires explicit opt-in."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.auth.admin import require_admin_imports
from app.security.import_authority import require_import_actor


class TestLegacySharedTokenRequiresOptIn:
    def test_shared_token_rejected_when_legacy_disabled(self, monkeypatch):
        import app.auth.admin as auth_admin

        class DefaultSettings:
            enable_admin_imports = True
            jwt_auth_enabled = False
            enable_legacy_admin_token = False
            enforce_jwt_mutations = True
            admin_token = "test-token"
            admin_review_token = "test-token"

        monkeypatch.setattr(auth_admin, "get_settings", lambda: DefaultSettings())

        with pytest.raises(HTTPException) as exc_info:
            require_import_actor(x_jta_admin_token="test-token", authorization=None)

        assert exc_info.value.status_code == 403

    def test_shared_token_allowed_only_with_local_opt_in(self, monkeypatch):
        import app.auth.admin as auth_admin

        class LegacyOptInSettings:
            enable_admin_imports = True
            jwt_auth_enabled = False
            enable_legacy_admin_token = True
            enforce_jwt_mutations = False
            admin_token = "test-token"
            admin_review_token = "test-token"

        monkeypatch.setattr(auth_admin, "get_settings", lambda: LegacyOptInSettings())

        actor = require_admin_imports(x_jta_admin_token="test-token", authorization=None)
        assert actor.auth_method == "shared_token"
        assert actor.role == "admin"
