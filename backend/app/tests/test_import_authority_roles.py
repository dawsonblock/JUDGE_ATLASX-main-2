"""Role-floor and JWT validation proofs for import authority helpers."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import HTTPException
from jose import jwt

import app.auth.admin as auth_admin
import app.auth.jwt_handler as jwt_handler
import app.security.import_authority as import_authority
from app.auth.actor import AdminActor
from app.auth.jwt_handler import create_access_token


class _Settings:
    jwt_auth_enabled = True
    enable_legacy_admin_token = False
    enforce_jwt_mutations = True
    enable_admin_imports = True
    enable_admin_review = True
    admin_token = "test-token"
    admin_review_token = "test-token"
    jwt_secret_key = "test-secret"
    jwt_algorithm = "HS256"
    jwt_access_token_expire_minutes = 15
    jwt_refresh_token_expire_days = 7


def _patch_settings(monkeypatch, settings_obj) -> None:
    monkeypatch.setattr(auth_admin, "get_settings", lambda: settings_obj)
    monkeypatch.setattr(jwt_handler, "get_settings", lambda: settings_obj)


def _bearer(role: str) -> str:
    token = create_access_token(email=f"{role}@example.test", role=role)
    return f"Bearer {token}"


def test_import_actor_requires_source_admin_floor(monkeypatch) -> None:
    settings = _Settings()
    _patch_settings(monkeypatch, settings)

    for role in ("viewer", "reviewer"):
        with pytest.raises(HTTPException) as exc_info:
            import_authority.require_import_actor(
                authorization=_bearer(role),
                x_jta_admin_token=None,
            )
        assert exc_info.value.status_code == 403

    actor = import_authority.require_import_actor(
        authorization=_bearer("source_admin"),
        x_jta_admin_token=None,
    )
    assert actor.role == "source_admin"
    assert actor.auth_method == "jwt"


def test_unknown_role_token_is_rejected(monkeypatch) -> None:
    settings = _Settings()
    _patch_settings(monkeypatch, settings)

    payload = {
        "sub": "unknown@example.test",
        "role": "alien_role",
        "type": "access",
        "jti": "unknown-role-token",
    }
    raw = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)

    with pytest.raises(HTTPException) as exc_info:
        import_authority.require_source_admin_actor(
            authorization=f"Bearer {raw}",
            x_jta_admin_token=None,
        )
    assert exc_info.value.status_code == 401


def test_malformed_and_expired_tokens_are_rejected(monkeypatch) -> None:
    settings = _Settings()
    _patch_settings(monkeypatch, settings)

    with pytest.raises(HTTPException) as malformed:
        import_authority.require_source_admin_actor(
            authorization="Bearer not.a.valid.jwt",
            x_jta_admin_token=None,
        )
    assert malformed.value.status_code == 401

    settings.jwt_access_token_expire_minutes = -1
    expired = create_access_token(email="expired@example.test", role="source_admin")
    with pytest.raises(HTTPException) as expired_exc:
        import_authority.require_source_admin_actor(
            authorization=f"Bearer {expired}",
            x_jta_admin_token=None,
        )
    assert expired_exc.value.status_code == 401


def test_jwt_required_when_mutation_enforcement_is_on(monkeypatch) -> None:
    settings = _Settings()
    _patch_settings(monkeypatch, settings)

    # Force shared-token path from require_admin_imports.
    monkeypatch.setattr(
        import_authority,
        "require_admin_imports",
        lambda x_jta_admin_token=None, authorization=None: AdminActor(
            actor_id="shared-admin-token",
            actor_type="shared_token",
            role="admin",
            auth_method="shared_token",
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        import_authority.require_import_actor(
            authorization=None,
            x_jta_admin_token="test-token",
        )
    assert exc_info.value.status_code == 403
