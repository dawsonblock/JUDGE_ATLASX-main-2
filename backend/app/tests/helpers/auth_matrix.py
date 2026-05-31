"""Reusable helpers for auth/RBAC matrix tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.auth.jwt_handler import create_access_token


@dataclass(frozen=True)
class AuthMatrixCase:
    """Single role/endpoint expectation for matrix testing."""

    role: str
    method: str
    path: str
    expected_allowed: bool
    body: dict[str, Any] | None = None


def make_jwt_for_role(email: str, role: str) -> dict[str, str]:
    """Return Authorization header dict for a JWT with the given role."""
    token = create_access_token(email=email, role=role)
    return {"Authorization": f"Bearer {token}"}


def assert_auth_matrix(response, case: AuthMatrixCase) -> None:
    """Assert role access expectation against an HTTP response."""
    status = response.status_code
    if case.expected_allowed:
        assert status not in (401, 403), (
            f"Role '{case.role}' should be ALLOWED on {case.method} {case.path}, "
            f"got HTTP {status}: {response.text[:200]}"
        )
    else:
        assert status in (401, 403), (
            f"Role '{case.role}' should be DENIED on {case.method} {case.path}, "
            f"got HTTP {status}: {response.text[:200]}"
        )
