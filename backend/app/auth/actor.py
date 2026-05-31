"""Admin actor identity for audit logging.

AdminActor encapsulates the identity of the principal performing an admin
action. It is designed so that raw secret tokens are NEVER used as actor
identity and never appear in audit logs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AdminRole = Literal["viewer", "reviewer", "source_admin", "admin", "owner"]
VALID_ADMIN_ROLES: tuple[AdminRole, ...] = (
    "viewer",
    "reviewer",
    "source_admin",
    "admin",
    "owner",
)
LEGACY_ROLE_ALIASES = {
    "system_admin": "admin",
}


def normalize_admin_role(role: str) -> AdminRole:
    """Normalize legacy role names and reject unknown role values."""
    normalized = LEGACY_ROLE_ALIASES.get(role, role)
    if normalized not in VALID_ADMIN_ROLES:
        raise ValueError(f"Unknown admin role: {role}")
    return normalized  # type: ignore[return-value]


@dataclass(frozen=True)
class AdminActor:
    """Stable, non-secret identity for an authenticated admin principal.

    actor_id should be a stable, human-readable label such as
    "shared-admin-token" — never the raw token value.
    """

    actor_id: str  # stable, non-secret label e.g. "shared-admin-token"
    actor_type: str  # "shared_token", "user", "service"
    role: AdminRole
    auth_method: str  # "shared_token", "jwt", "api_key"
    display_name: str | None = None
    email: str | None = None
