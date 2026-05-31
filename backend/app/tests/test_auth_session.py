"""Tests for server-side JWT session revocation (Phase 2 auth hardening).

Covers:
- login creates a UserSession
- refresh validates and rotates session
- logout revokes session
- revoked token fails on refresh
- expired token fails on refresh
- logout-all revokes all sessions
- inactive user cannot refresh
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.auth.jwt_handler import create_refresh_token, hash_password
from app.main import app
from app.models.entities import AuditLog, User, UserSession

client = TestClient(app)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _make_user(db, email: str = "session-test@example.com", role: str = "reviewer"):
    existing = db.query(User).filter(User.email == email).first()
    if existing:
        return existing
    user = User(
        email=email,
        hashed_password=hash_password("TestPassword123!"),
        role=role,
        is_active=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Unit tests (no HTTP) — exercise session helpers directly
# ---------------------------------------------------------------------------


class TestSessionHelpers:
    def test_hash_token_is_deterministic(self):
        raw = "my-secret-refresh-token"
        h1 = _hash_token(raw)
        h2 = _hash_token(raw)
        assert h1 == h2

    def test_hash_token_not_equal_to_raw(self):
        raw = "my-secret-refresh-token"
        assert _hash_token(raw) != raw

    def test_validate_session_raises_if_none(self):
        from app.api.routes.auth import _validate_session

        with pytest.raises(HTTPException) as exc:
            _validate_session(None)
        assert exc.value.status_code == 401

    def test_validate_session_raises_if_revoked(self):
        from app.api.routes.auth import _validate_session

        sess = MagicMock()
        sess.revoked_at = datetime.now(timezone.utc)
        sess.expires_at = datetime.now(timezone.utc) + timedelta(days=1)
        with pytest.raises(HTTPException) as exc:
            _validate_session(sess)
        assert exc.value.status_code == 401
        assert "revoked" in exc.value.detail.lower()

    def test_validate_session_raises_if_expired(self):
        from app.api.routes.auth import _validate_session

        sess = MagicMock()
        sess.revoked_at = None
        sess.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
        with pytest.raises(HTTPException) as exc:
            _validate_session(sess)
        assert exc.value.status_code == 401
        assert "expired" in exc.value.detail.lower()

    def test_validate_session_passes_for_valid_session(self):
        from app.api.routes.auth import _validate_session

        sess = MagicMock()
        sess.revoked_at = None
        sess.expires_at = datetime.now(timezone.utc) + timedelta(days=1)
        # Should not raise
        _validate_session(sess)


# ---------------------------------------------------------------------------
# Integration tests — require DB
# ---------------------------------------------------------------------------


class TestLoginCreatesSession:
    def test_login_rejects_username_field_payload(self, db_session):
        user = _make_user(db_session, email="schema-test@example.com")
        response = client.post(
            "/api/auth/login",
            json={"username": user.email, "password": "TestPassword123!"},
        )
        assert response.status_code == 422

    def test_login_creates_user_session(self, db_session):
        user = _make_user(db_session)
        response = client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "TestPassword123!"},
        )
        assert response.status_code == 200
        data = response.json()
        assert "refresh_token" in data
        assert "access_token" in data

        # Verify a session row was created
        token_hash = _hash_token(data["refresh_token"])
        db_session.expire_all()
        sess = (
            db_session.query(UserSession)
            .filter(UserSession.refresh_token_hash == token_hash)
            .first()
        )
        assert sess is not None
        assert sess.revoked_at is None
        assert sess.user_id == user.id

    def test_login_writes_audit_log(self, db_session):
        user = _make_user(db_session, email="audit-login@example.com")
        response = client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "TestPassword123!"},
        )
        assert response.status_code == 200
        db_session.expire_all()
        log = (
            db_session.query(AuditLog)
            .filter(AuditLog.action == "user.login", AuditLog.actor_id == user.email)
            .order_by(AuditLog.id.desc())
            .first()
        )
        assert log is not None


class TestRefreshRotatesSession:
    def test_refresh_returns_new_tokens(self, db_session):
        user = _make_user(db_session, email="refresh-test@example.com")
        login_resp = client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "TestPassword123!"},
        )
        assert login_resp.status_code == 200
        old_refresh = login_resp.json()["refresh_token"]

        refresh_resp = client.post(
            "/api/auth/refresh", json={"refresh_token": old_refresh}
        )
        assert refresh_resp.status_code == 200
        new_refresh = refresh_resp.json()["refresh_token"]
        assert new_refresh != old_refresh

    def test_refresh_revokes_old_session(self, db_session):
        user = _make_user(db_session, email="refresh-revoke@example.com")
        login_resp = client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "TestPassword123!"},
        )
        old_refresh = login_resp.json()["refresh_token"]
        old_hash = _hash_token(old_refresh)

        client.post("/api/auth/refresh", json={"refresh_token": old_refresh})

        db_session.expire_all()
        old_sess = (
            db_session.query(UserSession)
            .filter(UserSession.refresh_token_hash == old_hash)
            .first()
        )
        assert old_sess is not None
        assert old_sess.revoked_at is not None

    def test_revoked_token_fails_refresh(self, db_session):
        user = _make_user(db_session, email="revoked-refresh@example.com")
        login_resp = client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "TestPassword123!"},
        )
        old_refresh = login_resp.json()["refresh_token"]

        # First refresh — OK, rotates session
        client.post("/api/auth/refresh", json={"refresh_token": old_refresh})

        # Second refresh with same (now revoked) token — must fail
        resp2 = client.post("/api/auth/refresh", json={"refresh_token": old_refresh})
        assert resp2.status_code == 401

    def test_inactive_user_cannot_refresh(self, db_session):
        user = _make_user(db_session, email="inactive-refresh@example.com")
        login_resp = client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "TestPassword123!"},
        )
        refresh_token = login_resp.json()["refresh_token"]

        # Deactivate user
        user.is_active = False
        db_session.commit()

        resp = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        assert resp.status_code == 401


class TestLogout:
    def test_logout_revokes_session(self, db_session):
        user = _make_user(db_session, email="logout-test@example.com")
        login_resp = client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "TestPassword123!"},
        )
        refresh_token = login_resp.json()["refresh_token"]
        token_hash = _hash_token(refresh_token)

        resp = client.post("/api/auth/logout", json={"refresh_token": refresh_token})
        assert resp.status_code == 204

        db_session.expire_all()
        sess = (
            db_session.query(UserSession)
            .filter(UserSession.refresh_token_hash == token_hash)
            .first()
        )
        assert sess is not None
        assert sess.revoked_at is not None

    def test_logout_then_refresh_fails(self, db_session):
        user = _make_user(db_session, email="logout-no-refresh@example.com")
        login_resp = client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "TestPassword123!"},
        )
        refresh_token = login_resp.json()["refresh_token"]

        client.post("/api/auth/logout", json={"refresh_token": refresh_token})

        resp = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        assert resp.status_code == 401

    def test_logout_unknown_token_is_204(self):
        """Logout with an unknown token must be idempotent (204)."""
        resp = client.post(
            "/api/auth/logout", json={"refresh_token": "totally-unknown-token"}
        )
        assert resp.status_code == 204


class TestLogoutAll:
    def test_logout_all_revokes_all_sessions(self, db_session):
        user = _make_user(db_session, email="logout-all@example.com")

        # Create two sessions
        login1 = client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "TestPassword123!"},
        )
        login2 = client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "TestPassword123!"},
        )
        access_token = login1.json()["access_token"]
        r2 = login2.json()["refresh_token"]

        # logout-all with access token
        resp = client.post(
            "/api/auth/logout-all",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert resp.status_code == 204

        db_session.expire_all()
        active = (
            db_session.query(UserSession)
            .filter(
                UserSession.user_id == user.id,
                UserSession.revoked_at.is_(None),
            )
            .count()
        )
        assert active == 0

    def test_logout_all_then_any_refresh_fails(self, db_session):
        user = _make_user(db_session, email="logout-all-fail@example.com")
        login_resp = client.post(
            "/api/auth/login",
            json={"email": user.email, "password": "TestPassword123!"},
        )
        access_token = login_resp.json()["access_token"]
        refresh_token = login_resp.json()["refresh_token"]

        client.post(
            "/api/auth/logout-all",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        resp = client.post("/api/auth/refresh", json={"refresh_token": refresh_token})
        assert resp.status_code == 401

    def test_logout_all_requires_access_token(self):
        resp = client.post(
            "/api/auth/logout-all",
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert resp.status_code == 401
