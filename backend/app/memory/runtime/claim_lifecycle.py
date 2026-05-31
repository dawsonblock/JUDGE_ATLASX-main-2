"""Claim lifecycle — status enum, transitions, and lifecycle policy.

All logic is deterministic and DB-free; persistence is the caller's
responsibility.
"""

from __future__ import annotations

from enum import Enum
from dataclasses import dataclass, field
from typing import FrozenSet


class ClaimStatus(str, Enum):
    """Possible lifecycle states for a memory claim."""

    DRAFT = "draft"
    ACTIVE = "active"
    STALE = "stale"
    INVALIDATED = "invalidated"
    ARCHIVED = "archived"


# Valid forward transitions (no backward movement allowed).
_ALLOWED: dict[ClaimStatus, FrozenSet[ClaimStatus]] = {
    ClaimStatus.DRAFT: frozenset({ClaimStatus.ACTIVE, ClaimStatus.INVALIDATED}),
    ClaimStatus.ACTIVE: frozenset({ClaimStatus.STALE, ClaimStatus.INVALIDATED}),
    ClaimStatus.STALE: frozenset(
        {ClaimStatus.ACTIVE, ClaimStatus.INVALIDATED, ClaimStatus.ARCHIVED}
    ),
    ClaimStatus.INVALIDATED: frozenset({ClaimStatus.ARCHIVED}),
    ClaimStatus.ARCHIVED: frozenset(),
}


@dataclass
class ClaimTransition:
    """Record of a single lifecycle transition."""

    from_status: ClaimStatus
    to_status: ClaimStatus
    reason: str
    claim_key: str

    def is_valid(self) -> bool:
        """Return True if this transition is permitted by the state graph."""
        return self.to_status in _ALLOWED.get(self.from_status, frozenset())


@dataclass
class LifecyclePolicy:
    """Rules governing automatic claim lifecycle management.

    Attributes
    ----------
    stale_after_rebuilds:
        Number of rebuild cycles after which an untouched active claim
        becomes stale automatically.
    archive_after_invalidated:
        Number of rebuild cycles after which an invalidated claim should
        be archived.
    allow_reactivation:
        If True, stale claims may be moved back to active.
    hard_reasons:
        Set of invalidation reasons that can never be reactivated.
    """

    stale_after_rebuilds: int = 3
    archive_after_invalidated: int = 5
    allow_reactivation: bool = True
    hard_reasons: FrozenSet[str] = field(
        default_factory=lambda: frozenset(
            {"manual_reject", "source_rejected", "privacy_violation"}
        )
    )

    def should_go_stale(self, rebuilds_since_touch: int) -> bool:
        """Return True if a claim should become stale given rebuild count."""
        return rebuilds_since_touch >= self.stale_after_rebuilds

    def should_archive(self, rebuilds_since_invalidation: int) -> bool:
        """Return True if an invalidated claim should be archived."""
        return rebuilds_since_invalidation >= self.archive_after_invalidated

    def is_hard_invalidation(self, reason: str) -> bool:
        """Return True if *reason* is a hard invalidation that blocks reactivation."""
        return reason in self.hard_reasons

    def allowed_transitions(self, status: ClaimStatus) -> FrozenSet[ClaimStatus]:
        """Return the set of statuses reachable from *status*."""
        allowed = set(_ALLOWED.get(status, frozenset()))
        if not self.allow_reactivation:
            allowed.discard(ClaimStatus.ACTIVE)
        return frozenset(allowed)
