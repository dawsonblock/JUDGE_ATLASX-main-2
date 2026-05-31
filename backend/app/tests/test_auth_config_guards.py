"""Auth configuration guard tests for JWT-first fail-closed behavior."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.auth.actor import AdminActor
from app.auth.admin import (
    enforce_jwt_mutation_authority,
    require_admin_imports,
    require_admin_token,
)


class _LegacyDisabledSettings:
    jwt_auth_enabled = False
    enable_legacy_admin_token = False
    enforce_jwt_mutations = True
    enable_admin_imports = True
    admin_token = "test-token"
    admin_review_token = "test-token"


class _LegacyEnabledSettings:
    jwt_auth_enabled = False
    enable_legacy_admin_token = True
    enforce_jwt_mutations = False
    enable_admin_imports = True
    admin_token = "test-token"
    admin_review_token = "test-token"


def test_require_admin_token_fails_closed_when_legacy_disabled(monkeypatch) -> None:
    import app.auth.admin as auth_admin

    monkeypatch.setattr(auth_admin, "get_settings", lambda: _LegacyDisabledSettings())

    with pytest.raises(HTTPException) as exc_info:
        require_admin_token(x_jta_admin_token="test-token", authorization=None)

    assert exc_info.value.status_code == 403
    assert "legacy" in exc_info.value.detail.lower()


def test_require_admin_imports_fails_closed_when_legacy_disabled(monkeypatch) -> None:
    import app.auth.admin as auth_admin

    monkeypatch.setattr(auth_admin, "get_settings", lambda: _LegacyDisabledSettings())

    with pytest.raises(HTTPException) as exc_info:
        require_admin_imports(x_jta_admin_token="test-token", authorization=None)

    assert exc_info.value.status_code == 403
    assert "legacy" in exc_info.value.detail.lower()


def test_require_admin_token_allows_legacy_when_explicitly_enabled(monkeypatch) -> None:
    import app.auth.admin as auth_admin

    monkeypatch.setattr(auth_admin, "get_settings", lambda: _LegacyEnabledSettings())

    actor = require_admin_token(x_jta_admin_token="test-token", authorization=None)

    assert actor.auth_method == "shared_token"
    assert actor.actor_id == "shared-admin-token"


def test_enforce_jwt_mutation_authority_rejects_shared_token_actor(monkeypatch) -> None:
    import app.auth.admin as auth_admin

    monkeypatch.setattr(auth_admin, "get_settings", lambda: _LegacyDisabledSettings())

    shared_actor = AdminActor(
        actor_id="shared-admin-token",
        actor_type="shared_token",
        role="admin",
        auth_method="shared_token",
    )

    with pytest.raises(HTTPException) as exc_info:
        enforce_jwt_mutation_authority(shared_actor)

    assert exc_info.value.status_code == 403
    assert "jwt" in exc_info.value.detail.lower()


def test_enforce_jwt_mutation_authority_allows_shared_token_when_disabled(
    monkeypatch,
) -> None:
    import app.auth.admin as auth_admin

    monkeypatch.setattr(auth_admin, "get_settings", lambda: _LegacyEnabledSettings())

    shared_actor = AdminActor(
        actor_id="shared-admin-token",
        actor_type="shared_token",
        role="admin",
        auth_method="shared_token",
    )

    assert enforce_jwt_mutation_authority(shared_actor) is shared_actor
