"""JWT token creation and verification for JudgeTracker Atlas.

Supports access tokens (short-lived) and refresh tokens (longer-lived).
Tokens carry: sub (user email), role, type ("access" | "refresh"), jti (unique ID).

The `jti` claim ensures each refresh token is unique even if issued within
the same second — required for server-side session revocation.
"""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.auth.actor import normalize_admin_role
from app.core.config import get_settings

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ---------------------------------------------------------------------------
# Password helpers
# ---------------------------------------------------------------------------


def hash_password(plain: str) -> str:
    """Return a bcrypt hash of *plain*."""
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Return True if *plain* matches *hashed*."""
    return _pwd_context.verify(plain, hashed)


# ---------------------------------------------------------------------------
# Token creation
# ---------------------------------------------------------------------------


def _make_token(
    subject: str,
    role: str,
    token_type: str,
    expire_delta: timedelta,
) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "role": role,
        "type": token_type,
        "jti": secrets.token_hex(16),  # unique per-token ID for session tracking
        "iat": now,
        "exp": now + expire_delta,
    }
    return jwt.encode(
        payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm
    )


def create_access_token(email: str, role: str) -> str:
    settings = get_settings()
    return _make_token(
        subject=email,
        role=normalize_admin_role(role),
        token_type="access",
        expire_delta=timedelta(minutes=settings.jwt_access_token_expire_minutes),
    )


def create_refresh_token(email: str, role: str) -> str:
    settings = get_settings()
    return _make_token(
        subject=email,
        role=normalize_admin_role(role),
        token_type="refresh",
        expire_delta=timedelta(days=settings.jwt_refresh_token_expire_days),
    )


# ---------------------------------------------------------------------------
# Token verification
# ---------------------------------------------------------------------------


class TokenPayload:
    def __init__(self, email: str, role: str, token_type: str) -> None:
        self.email = email
        self.role = role
        self.token_type = token_type


def decode_token(token: str) -> TokenPayload:
    """Decode and validate a JWT.  Raises ValueError on any failure."""
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )
    except JWTError as exc:
        raise ValueError(f"Invalid token: {exc}") from exc

    sub = payload.get("sub")
    role = payload.get("role")
    token_type = payload.get("type")

    if not sub or not role or not token_type:
        raise ValueError("Token missing required claims")

    return TokenPayload(
        email=sub, role=normalize_admin_role(role), token_type=token_type
    )
