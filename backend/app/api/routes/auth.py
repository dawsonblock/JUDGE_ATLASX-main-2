"""Auth API routes: register, login, refresh, logout, and current-user.

These endpoints back the JWT authentication system.  The shared-token
auth path in admin.py remains active until jwt_auth_enabled=True and
at least one admin user record exists.

Phase 2 hardening: refresh tokens are server-side revocable via UserSession.
Login creates a session, refresh validates and rotates the session, logout
revokes it, logout-all revokes all sessions for the user.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app.auth.actor import AdminActor, AdminRole, normalize_admin_role
from app.auth.jwt_handler import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.audit.append_log import append_audit_entry
from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import User, UserSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# Session helpers
# ---------------------------------------------------------------------------


def _hash_token(raw_token: str) -> str:
    """Return a SHA-256 hex digest of the raw token. Never store raw tokens."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


def _create_session(
    db: Session,
    user: User,
    refresh_token: str,
    request: Request | None,
    expire_days: int,
) -> UserSession:
    """Persist a new UserSession for the given user and raw refresh token."""
    now = datetime.now(timezone.utc)
    ua = (request.headers.get("User-Agent") or "")[:512] if request else None
    ip_raw = _client_ip(request) if request else None
    ip_hash = hashlib.sha256(ip_raw.encode()).hexdigest()[:128] if ip_raw else None

    session = UserSession(
        user_id=user.id,
        refresh_token_hash=_hash_token(refresh_token),
        expires_at=now + timedelta(days=expire_days),
        user_agent=ua,
        ip_hash=ip_hash,
    )
    db.add(session)
    return session


def _lookup_session(db: Session, refresh_token: str) -> UserSession | None:
    """Return the UserSession matching this raw refresh token hash, or None."""
    token_hash = _hash_token(refresh_token)
    return (
        db.query(UserSession)
        .filter(UserSession.refresh_token_hash == token_hash)
        .first()
    )


def _validate_session(session: UserSession | None) -> None:
    """Raise 401 if the session is missing, revoked, or expired."""
    if session is None:
        raise HTTPException(status_code=401, detail="Session not found")
    if session.revoked_at is not None:
        raise HTTPException(status_code=401, detail="Session has been revoked")
    # SQLite stores naive datetimes; normalize for comparison
    now = datetime.now(timezone.utc)
    expires = session.expires_at
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires < now:
        raise HTTPException(status_code=401, detail="Session has expired")


# ---------------------------------------------------------------------------
# Request / response shapes
# ---------------------------------------------------------------------------


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    display_name: str | None = None
    role: str = "viewer"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class MeResponse(BaseModel):
    email: str
    role: str
    display_name: str | None
    is_active: bool


# ---------------------------------------------------------------------------
# Helper: extract Bearer token from Authorization header
# ---------------------------------------------------------------------------


def _extract_bearer(authorization: str | None) -> str:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401, detail="Missing or invalid Authorization header"
        )
    return authorization.removeprefix("Bearer ").strip()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("/register", status_code=201)
def register(
    body: RegisterRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict:
    """Create a new admin user.

    The first registered user always gets ``owner`` role regardless
    of the requested role.  Subsequent registrations require an existing
    owner to be authenticated (enforced by checking the
    ``Authorization`` header when users already exist).
    """
    settings = get_settings()

    existing_count: int = db.query(User).count()
    is_bootstrap = existing_count == 0

    # In non-development environments, require a bootstrap secret for first-user creation
    if is_bootstrap and settings.app_env != "development":
        bootstrap_secret = request.headers.get("X-JTA-Bootstrap-Secret")
        if not settings.first_admin_secret:
            raise HTTPException(
                status_code=503,
                detail="Bootstrap not available: JTA_FIRST_ADMIN_SECRET is not configured.",
            )
        if bootstrap_secret != settings.first_admin_secret:
            raise HTTPException(
                status_code=403,
                detail="Invalid bootstrap secret.",
            )

    # After bootstrap, require jwt-authenticated owner
    if not is_bootstrap:
        auth_header = request.headers.get("Authorization")
        token = _extract_bearer(auth_header)
        try:
            payload = decode_token(token)
        except ValueError as exc:
            raise HTTPException(status_code=401, detail=str(exc))
        if payload.token_type != "access":
            raise HTTPException(status_code=401, detail="Access token required")
        if normalize_admin_role(payload.role) != "owner":
            raise HTTPException(
                status_code=403, detail="Only owner may register new users"
            )

    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")

    _validate_password_strength(body.password)

    try:
        requested_role = normalize_admin_role(body.role)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    assigned_role: AdminRole = "owner" if is_bootstrap else requested_role

    user = User(
        email=body.email,
        hashed_password=hash_password(body.password),
        role=assigned_role,
        display_name=body.display_name,
        is_active=True,
    )
    db.add(user)
    db.flush()

    append_audit_entry(
        db,
        action="user.register",
        entity_type="user",
        entity_id=str(user.id),
        actor_id=body.email,
        actor_type="user",
        actor_role=assigned_role,
        actor_ip=_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )
    db.commit()

    return {"id": user.id, "email": user.email, "role": user.role}


@router.post("/login")
def login(
    body: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Exchange email + password for JWT access and refresh tokens.

    Creates a server-side UserSession so that the refresh token can be
    revoked server-side via /auth/logout or /auth/logout-all.
    """
    settings = get_settings()
    user: User | None = db.query(User).filter(User.email == body.email).first()

    # Constant-time path regardless of user existence to prevent user enumeration
    dummy_hash = "$2b$12$KIXtSFl0u6OXo9yEUv1AqeHU4WFn0sBfJQv9JR7Ogh.dkGJPMRrFC"
    ok = verify_password(body.password, user.hashed_password if user else dummy_hash)

    if not user or not ok or not user.is_active:
        logger.warning("login.failed email=%s ip=%s", body.email, _client_ip(request))
        raise HTTPException(status_code=401, detail="Invalid credentials")

    refresh_token = create_refresh_token(user.email, user.role)

    # Create server-side session
    user.last_login_at = datetime.now(timezone.utc)
    _create_session(
        db, user, refresh_token, request, settings.jwt_refresh_token_expire_days
    )
    append_audit_entry(
        db,
        action="user.login",
        entity_type="user",
        entity_id=str(user.id),
        actor_id=user.email,
        actor_type="user",
        actor_role=user.role,
        actor_ip=_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )
    db.commit()

    return TokenResponse(
        access_token=create_access_token(user.email, user.role),
        refresh_token=refresh_token,
    )


@router.post("/refresh")
def refresh_tokens(
    body: RefreshRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    """Exchange a valid refresh token for a new access + refresh token pair.

    Validates the token against the server-side UserSession record.
    The old session is revoked and a new session is created (token rotation).
    """
    settings = get_settings()
    try:
        payload = decode_token(body.refresh_token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    if payload.token_type != "refresh":
        raise HTTPException(status_code=401, detail="Refresh token required")

    # Server-side session check
    session = _lookup_session(db, body.refresh_token)
    _validate_session(session)

    user: User | None = db.query(User).filter(User.email == payload.email).first()
    if not user or not user.is_active:
        logger.warning("refresh.failed email=%s (inactive/not found)", payload.email)
        raise HTTPException(status_code=401, detail="User not found or inactive")

    # Rotate: revoke old session, create new one
    now = datetime.now(timezone.utc)
    session.revoked_at = now  # type: ignore[union-attr]

    new_refresh_token = create_refresh_token(user.email, user.role)
    _create_session(
        db, user, new_refresh_token, request, settings.jwt_refresh_token_expire_days
    )
    append_audit_entry(
        db,
        action="user.token_refresh",
        entity_type="user",
        entity_id=str(user.id),
        actor_id=user.email,
        actor_type="user",
        actor_role=user.role,
        actor_ip=_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )
    db.commit()

    return TokenResponse(
        access_token=create_access_token(user.email, user.role),
        refresh_token=new_refresh_token,
    )


@router.post("/logout", status_code=204)
def logout(
    body: RefreshRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> None:
    """Revoke the current refresh token session.

    Accepts the refresh token in the request body and marks the matching
    server-side session as revoked.  Returns 204 on success.  Also returns
    204 if the token is already expired or not found (idempotent).
    """
    session = _lookup_session(db, body.refresh_token)
    if session is not None and session.revoked_at is None:
        session.revoked_at = datetime.now(timezone.utc)
        # Audit: best-effort — resolve user for audit log
        user = db.query(User).filter(User.id == session.user_id).first()
        if user:
            append_audit_entry(
                db,
                action="user.logout",
                entity_type="user",
                entity_id=str(user.id),
                actor_id=user.email,
                actor_type="user",
                actor_role=user.role,
                actor_ip=_client_ip(request),
                user_agent=request.headers.get("User-Agent"),
            )
        db.commit()


@router.post("/logout-all", status_code=204)
def logout_all(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> None:
    """Revoke all active sessions for the currently authenticated user.

    Requires a valid access token.  All non-revoked sessions are marked
    revoked.  Returns 204 on success.
    """
    token = _extract_bearer(authorization)
    try:
        payload = decode_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    if payload.token_type != "access":
        raise HTTPException(status_code=401, detail="Access token required")

    user: User | None = db.query(User).filter(User.email == payload.email).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    now = datetime.now(timezone.utc)
    revoked_count = 0
    for sess in (
        db.query(UserSession)
        .filter(
            UserSession.user_id == user.id,
            UserSession.revoked_at.is_(None),
        )
        .all()
    ):
        sess.revoked_at = now
        revoked_count += 1

    append_audit_entry(
        db,
        action="user.logout_all",
        entity_type="user",
        entity_id=str(user.id),
        actor_id=user.email,
        actor_type="user",
        actor_role=user.role,
        payload={"revoked_sessions": revoked_count},
    )
    db.commit()




@router.get("/me")
def me(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> MeResponse:
    """Return the profile of the currently authenticated user."""
    token = _extract_bearer(authorization)
    try:
        payload = decode_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    if payload.token_type != "access":
        raise HTTPException(status_code=401, detail="Access token required")

    user: User | None = db.query(User).filter(User.email == payload.email).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return MeResponse(
        email=user.email,
        role=user.role,
        display_name=user.display_name,
        is_active=user.is_active,
    )


# ---------------------------------------------------------------------------
# Dependency: require_jwt_user — usable as FastAPI Depends target
# ---------------------------------------------------------------------------


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> AdminActor:
    """FastAPI dependency that validates a Bearer JWT and returns an AdminActor."""
    token = _extract_bearer(authorization)
    try:
        payload = decode_token(token)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc))

    if payload.token_type != "access":
        raise HTTPException(status_code=401, detail="Access token required")

    user: User | None = db.query(User).filter(User.email == payload.email).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return AdminActor(
        actor_id=user.email,
        actor_type="user",
        role=user.role,  # type: ignore[arg-type]
        auth_method="jwt",
        display_name=user.display_name,
        email=user.email,
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _client_ip(request: Request) -> str | None:
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def _validate_password_strength(password: str) -> None:
    """Enforce minimum password requirements. Raises HTTPException on failure."""
    if len(password) < 12:
        raise HTTPException(
            status_code=422,
            detail="Password must be at least 12 characters",
        )
    if not any(c.isupper() for c in password):
        raise HTTPException(
            status_code=422,
            detail="Password must contain at least one uppercase letter",
        )
    if not any(c.isdigit() for c in password):
        raise HTTPException(
            status_code=422,
            detail="Password must contain at least one digit",
        )
