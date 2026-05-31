"""FastAPI route dependency helpers that enforce JWT + RBAC."""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.auth.actor import AdminActor, normalize_admin_role
from app.auth.jwt_handler import decode_token as _decode_token

_bearer = HTTPBearer(auto_error=False)


def require_jwt(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """Dependency: validates Bearer JWT and returns the decoded claims dict.

    Raises HTTP 401 if the token is absent or invalid.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing Bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        token_payload = _decode_token(credentials.credentials)
    except (ValueError, Exception):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return {
        "email": token_payload.email,
        "role": token_payload.role,
        "token_type": token_payload.token_type,
    }


def require_jwt_actor(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> AdminActor:
    """Validate a Bearer JWT and convert it into an AdminActor."""
    claims = require_jwt(credentials)
    return AdminActor(
        actor_id=claims["email"],
        actor_type="user",
        role=normalize_admin_role(claims["role"]),
        auth_method="jwt",
        email=claims["email"],
    )
