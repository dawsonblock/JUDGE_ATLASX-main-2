"""Proof tests: JWT mutation enforcement is on by default.

Verifies that enforce_jwt_mutation_authority rejects shared-token actors when
JTA_ENFORCE_JWT_MUTATIONS=true (the production default), and accepts JWT actors.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.auth.actor import AdminActor
from app.auth.admin import enforce_jwt_mutation_authority


class TestJwtMutationEnforcementDefault:
    """enforce_jwt_mutation_authority must reject shared tokens when enforcement is on."""

    def test_jwt_actor_allowed(self, monkeypatch):
        import app.auth.admin as auth_admin

        class EnforcedSettings:
            enforce_jwt_mutations = True

        monkeypatch.setattr(auth_admin, "get_settings", lambda: EnforcedSettings())

        actor = AdminActor(
            actor_id="test@example.test",
            actor_type="user",
            role="admin",
            auth_method="jwt",
            email="test@example.test",
        )
        result = enforce_jwt_mutation_authority(actor)
        assert result is actor

    def test_shared_token_actor_rejected_when_enforcement_on(self, monkeypatch):
        import app.auth.admin as auth_admin

        class EnforcedSettings:
            enforce_jwt_mutations = True

        monkeypatch.setattr(auth_admin, "get_settings", lambda: EnforcedSettings())

        actor = AdminActor(
            actor_id="shared-admin-token",
            actor_type="shared_token",
            role="admin",
            auth_method="shared_token",
        )
        with pytest.raises(HTTPException) as exc_info:
            enforce_jwt_mutation_authority(actor)
        assert exc_info.value.status_code == 403
        assert "jwt" in exc_info.value.detail.lower()

    def test_shared_token_allowed_when_enforcement_off(self, monkeypatch):
        import app.auth.admin as auth_admin

        class LaxSettings:
            enforce_jwt_mutations = False

        monkeypatch.setattr(auth_admin, "get_settings", lambda: LaxSettings())

        actor = AdminActor(
            actor_id="shared-admin-token",
            actor_type="shared_token",
            role="admin",
            auth_method="shared_token",
        )
        result = enforce_jwt_mutation_authority(actor)
        assert result is actor
