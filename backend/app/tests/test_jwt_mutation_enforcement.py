from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.auth.actor import AdminActor
from app.auth.admin import enforce_jwt_mutation_authority


def _shared_actor() -> AdminActor:
    return AdminActor(
        actor_id="shared-admin-token",
        actor_type="shared_token",
        role="owner",
        auth_method="shared_token",
    )


def _jwt_actor() -> AdminActor:
    return AdminActor(
        actor_id="reviewer@example.test",
        actor_type="user",
        role="reviewer",
        auth_method="jwt",
        email="reviewer@example.test",
    )


def test_shared_token_allowed_when_enforcement_off() -> None:
    class SettingsOff:
        enforce_jwt_mutations = False

    with patch("app.auth.admin.get_settings", return_value=SettingsOff()):
        actor = enforce_jwt_mutation_authority(_shared_actor())
    assert actor.auth_method == "shared_token"


def test_shared_token_blocked_when_enforcement_on() -> None:
    class SettingsOn:
        enforce_jwt_mutations = True

    with patch("app.auth.admin.get_settings", return_value=SettingsOn()):
        with pytest.raises(HTTPException) as exc_info:
            enforce_jwt_mutation_authority(_shared_actor())

    assert exc_info.value.status_code == 403
    assert "JWT authentication is required" in str(exc_info.value.detail)


def test_jwt_actor_allowed_when_enforcement_on() -> None:
    class SettingsOn:
        enforce_jwt_mutations = True

    with patch("app.auth.admin.get_settings", return_value=SettingsOn()):
        actor = enforce_jwt_mutation_authority(_jwt_actor())
    assert actor.auth_method == "jwt"
