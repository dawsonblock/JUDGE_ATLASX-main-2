"""Permission constants and capability checks for JUDGE_ATLAS admin actions."""
from __future__ import annotations

# Action → required role mapping
MUTATION_PERMISSIONS: dict[str, set[str]] = {
    "source:create": {"admin", "owner"},
    "source:update": {"admin", "owner"},
    "source:delete": {"owner"},
    "review:approve": {"reviewer", "admin", "owner"},
    "review:reject": {"reviewer", "admin", "owner"},
    "review:flag": {"reviewer", "admin", "owner"},
    "review:override": {"admin", "owner"},
    "incident:publish": {"admin", "owner"},
    "incident:unpublish": {"admin", "owner"},
    "ingestion:run": {"admin", "owner"},
    "audit:read": {"admin", "owner"},
}

READ_PERMISSIONS: dict[str, set[str]] = {
    "source:read": {"viewer", "reviewer", "admin", "owner"},
    "review:read": {"reviewer", "admin", "owner"},
    "audit:read": {"admin", "owner"},
}


def can(role: str, action: str) -> bool:
    """Return True if *role* is allowed to perform *action*."""
    allowed = MUTATION_PERMISSIONS.get(action) or READ_PERMISSIONS.get(action)
    if allowed is None:
        return False
    return role in allowed


def assert_can(role: str, action: str) -> None:
    """Raise PermissionError if *role* cannot perform *action*."""
    if not can(role, action):
        raise PermissionError(f"Role '{role}' is not permitted to perform '{action}'")
