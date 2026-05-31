"""Tests for JWT creation, verification, and auth actor role normalization.

Covers the pure-function layer of app.auth — no DB or HTTP required:
- create_access_token / create_refresh_token: round-trip via decode_token,
  token_type field, jti uniqueness (raw-string differs across calls)
- decode_token: happy path (access, refresh), tampered token, expired token,
  token with each missing required claim (sub / role / type), junk input
- verify_password / hash_password: correctness and non-determinism
- normalize_admin_role: all valid roles pass through unchanged,
  invalid role raises ValueError
- AdminActor: frozen-dataclass semantics, field accessibility
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt as _jose_jwt

from app.auth.actor import VALID_ADMIN_ROLES, AdminActor, normalize_admin_role
from app.auth.jwt_handler import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.core.config import get_settings


# ---------------------------------------------------------------------------
# create_access_token / create_refresh_token round-trips
# ---------------------------------------------------------------------------


class TestCreateAndDecodeToken:
    def test_access_token_type_claim(self):
        token = create_access_token("test@example.com", "reviewer")
        payload = decode_token(token)
        assert payload.token_type == "access"

    def test_access_token_email_preserved(self):
        token = create_access_token("user@example.com", "admin")
        payload = decode_token(token)
        assert payload.email == "user@example.com"

    def test_access_token_role_preserved(self):
        token = create_access_token("user@example.com", "viewer")
        payload = decode_token(token)
        assert payload.role == "viewer"

    def test_refresh_token_type_claim(self):
        token = create_refresh_token("user@example.com", "reviewer")
        payload = decode_token(token)
        assert payload.token_type == "refresh"

    def test_two_access_tokens_are_distinct(self):
        """jti is random per-token so consecutive tokens must differ."""
        t1 = create_access_token("same@example.com", "reviewer")
        t2 = create_access_token("same@example.com", "reviewer")
        assert t1 != t2


# ---------------------------------------------------------------------------
# decode_token — error cases
# ---------------------------------------------------------------------------


class TestDecodeTokenErrors:
    def test_tampered_token_raises_value_error(self):
        token = create_access_token("test@example.com", "reviewer")
        tampered = token + "x"
        with pytest.raises(ValueError, match="Invalid token"):
            decode_token(tampered)

    def test_expired_token_raises_value_error(self):
        settings = get_settings()
        now = datetime.now(timezone.utc)
        expired_payload = {
            "sub": "expired@example.com",
            "role": "reviewer",
            "type": "access",
            "jti": "test-jti-expired",
            "iat": now - timedelta(hours=2),
            "exp": now - timedelta(hours=1),
        }
        expired_token = _jose_jwt.encode(
            expired_payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        with pytest.raises(ValueError, match="Invalid token"):
            decode_token(expired_token)

    def test_token_missing_role_raises_value_error(self):
        settings = get_settings()
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "no-role@example.com",
            "type": "access",
            "jti": "test-jti-missing-role",
            "iat": now,
            "exp": now + timedelta(hours=1),
        }
        token = _jose_jwt.encode(
            payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
        )
        with pytest.raises(ValueError, match="missing required claims"):
            decode_token(token)

    def test_token_missing_sub_raises_value_error(self):
        settings = get_settings()
        now = datetime.now(timezone.utc)
        payload = {
            "role": "reviewer",
            "type": "access",
            "jti": "test-jti-missing-sub",
            "iat": now,
            "exp": now + timedelta(hours=1),
        }
        token = _jose_jwt.encode(
            payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
        )
        with pytest.raises(ValueError, match="missing required claims"):
            decode_token(token)

    def test_token_missing_type_raises_value_error(self):
        settings = get_settings()
        now = datetime.now(timezone.utc)
        payload = {
            "sub": "no-type@example.com",
            "role": "reviewer",
            "jti": "test-jti-missing-type",
            "iat": now,
            "exp": now + timedelta(hours=1),
        }
        token = _jose_jwt.encode(
            payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
        )
        with pytest.raises(ValueError, match="missing required claims"):
            decode_token(token)

    def test_junk_string_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid token"):
            decode_token("not.a.jwt")


# ---------------------------------------------------------------------------
# verify_password / hash_password
# ---------------------------------------------------------------------------


class TestPasswordUtilities:
    def test_verify_password_correct_plain_text(self):
        plain = "SecurePass123!"
        hashed = hash_password(plain)
        assert verify_password(plain, hashed) is True

    def test_verify_password_wrong_plain_text(self):
        hashed = hash_password("RightPassword1!")
        assert verify_password("WrongPassword!", hashed) is False

    def test_hash_password_is_non_deterministic(self):
        """bcrypt uses a random salt so two hashes of the same input must differ."""
        plain = "SamePlainText99!"
        h1 = hash_password(plain)
        h2 = hash_password(plain)
        assert h1 != h2

    def test_both_hashes_cross_verify_correctly(self):
        """Both hashes produced from the same plain text validate correctly."""
        plain = "CrossVerify77!"
        h1 = hash_password(plain)
        h2 = hash_password(plain)
        assert verify_password(plain, h1) is True
        assert verify_password(plain, h2) is True


# ---------------------------------------------------------------------------
# normalize_admin_role
# ---------------------------------------------------------------------------


class TestNormalizeAdminRole:
    @pytest.mark.parametrize("role", list(VALID_ADMIN_ROLES))
    def test_valid_roles_pass_through_unchanged(self, role):
        assert normalize_admin_role(role) == role

    def test_unknown_role_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown admin role"):
            normalize_admin_role("superuser")

    def test_another_unknown_role_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown admin role"):
            normalize_admin_role("root")


# ---------------------------------------------------------------------------
# AdminActor — frozen dataclass semantics
# ---------------------------------------------------------------------------


class TestAdminActorFrozen:
    def test_admin_actor_is_frozen(self):
        actor = AdminActor(
            actor_id="test-actor",
            actor_type="user",
            role="reviewer",
            auth_method="jwt",
        )
        with pytest.raises((dataclasses.FrozenInstanceError, AttributeError)):
            actor.actor_id = "tampered"  # type: ignore[misc]

    def test_admin_actor_fields_accessible(self):
        actor = AdminActor(
            actor_id="reporter@example.com",
            actor_type="user",
            role="admin",
            auth_method="jwt",
            display_name="Reporter",
            email="reporter@example.com",
        )
        assert actor.actor_id == "reporter@example.com"
        assert actor.role == "admin"
        assert actor.display_name == "Reporter"
        assert actor.email == "reporter@example.com"
