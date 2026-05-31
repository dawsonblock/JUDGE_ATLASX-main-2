"""Proof that shared-token mutation paths are not enabled by default."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.security.import_authority import require_import_actor


def test_shared_token_import_access_is_not_globally_enabled(monkeypatch):
    import app.auth.admin as auth_admin

    class StrictSettings:
        enable_admin_imports = True
        jwt_auth_enabled = True
        enable_legacy_admin_token = False
        enforce_jwt_mutations = True
        admin_token = "test-token"
        admin_review_token = "test-token"

    monkeypatch.setattr(auth_admin, "get_settings", lambda: StrictSettings())

    with pytest.raises(HTTPException) as exc_info:
        require_import_actor(x_jta_admin_token="test-token", authorization=None)

    assert exc_info.value.status_code == 403
