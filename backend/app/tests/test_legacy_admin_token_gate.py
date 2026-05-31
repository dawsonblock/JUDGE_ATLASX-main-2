"""Tests for Phase 3: legacy shared-token admin path disabled by default.

Verifies:
- ENABLE_LEGACY_ADMIN_TOKEN defaults to False
- shared-token is rejected when enable_legacy_admin_token=False
- shared-token is accepted when enable_legacy_admin_token=True (dev only)
- startup warning emitted when legacy path is enabled
"""

from __future__ import annotations

import types

import pytest
from fastapi import HTTPException


def _fake_settings(**overrides) -> types.SimpleNamespace:
    defaults = dict(
        admin_token="test-secret-token",
        admin_review_token=None,
        jwt_auth_enabled=False,
        enable_legacy_admin_token=False,
    )
    defaults.update(overrides)
    return types.SimpleNamespace(**defaults)


class TestLegacyAdminTokenDisabledByDefault:
    def test_default_is_false(self):
        """Settings.enable_legacy_admin_token must default to False.

        We test this by checking the default value, unaffected by test env overrides.
        The test env sets JTA_ENABLE_LEGACY_ADMIN_TOKEN=true for other test compatibility,
        so we test the field default directly via the schema, not via Settings().
        """
        from pydantic_settings import BaseSettings

        from app.core.config import Settings

        # Check that the field default is False (not reading from env)
        field_info = Settings.model_fields.get("enable_legacy_admin_token")
        assert field_info is not None
        assert field_info.default is False, (
            "enable_legacy_admin_token must default to False in production. "
            "The test env overrides this for test compatibility only."
        )

    def test_shared_token_rejected_when_disabled(self):
        """require_admin_token must raise 403 when legacy token is disabled."""
        from unittest.mock import patch

        from app.auth.admin import require_admin_token

        with patch(
            "app.auth.admin.get_settings",
            return_value=_fake_settings(enable_legacy_admin_token=False),
        ):
            with pytest.raises(HTTPException) as exc:
                require_admin_token(x_jta_admin_token="test-secret-token")
            assert exc.value.status_code == 403
            assert "disabled" in exc.value.detail.lower() or "jwt" in exc.value.detail.lower()

    def test_shared_token_accepted_when_enabled(self):
        """require_admin_token accepts shared token when explicitly enabled."""
        import warnings
        from unittest.mock import patch

        from app.auth.actor import AdminActor
        from app.auth.admin import require_admin_token

        with patch(
            "app.auth.admin.get_settings",
            return_value=_fake_settings(enable_legacy_admin_token=True),
        ):
            with warnings.catch_warnings(record=True):
                warnings.simplefilter("always")
                actor = require_admin_token(x_jta_admin_token="test-secret-token")

        assert isinstance(actor, AdminActor)
        assert actor.actor_id == "shared-admin-token"

    def test_startup_warning_when_legacy_enabled(self):
        """A DeprecationWarning must be emitted when legacy path is used."""
        import warnings
        from unittest.mock import patch

        from app.auth.admin import require_admin_token

        with patch(
            "app.auth.admin.get_settings",
            return_value=_fake_settings(enable_legacy_admin_token=True),
        ):
            with warnings.catch_warnings(record=True) as w:
                warnings.simplefilter("always")
                require_admin_token(x_jta_admin_token="test-secret-token")
            assert any(issubclass(warning.category, DeprecationWarning) for warning in w)

    def test_wrong_token_still_rejected_when_legacy_enabled(self):
        """Wrong token value must be rejected even when legacy path is enabled."""
        from unittest.mock import patch

        from app.auth.admin import require_admin_token

        with patch(
            "app.auth.admin.get_settings",
            return_value=_fake_settings(enable_legacy_admin_token=True),
        ):
            with pytest.raises(HTTPException) as exc:
                require_admin_token(x_jta_admin_token="wrong-token")
            assert exc.value.status_code == 403

    def test_jwt_path_unaffected_by_legacy_flag(self):
        """JWT path must work regardless of enable_legacy_admin_token setting."""
        import secrets
        from datetime import timedelta

        from app.auth.jwt_handler import create_access_token

        token = create_access_token("admin@example.test", "admin")

        from unittest.mock import patch

        from app.auth.admin import require_admin_token

        fake_settings = types.SimpleNamespace(
            admin_token="test-secret-token",
            admin_review_token=None,
            jwt_auth_enabled=True,
            enable_legacy_admin_token=False,
            jwt_secret_key=__import__(
                "app.core.config", fromlist=["get_settings"]
            ).get_settings().jwt_secret_key,
            jwt_algorithm="HS256",
        )

        with patch("app.auth.admin.get_settings", return_value=fake_settings):
            actor = require_admin_token(authorization=f"Bearer {token}")

        assert actor.auth_method == "jwt"
        assert actor.actor_id == "admin@example.test"
