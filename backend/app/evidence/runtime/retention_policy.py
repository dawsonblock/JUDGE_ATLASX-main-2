"""Retention policy — TTL-based tiers for evidence lifecycle management."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class RetentionTier(str, Enum):
    """Ordered retention tiers from longest to shortest lifespan."""

    PERMANENT = "permanent"
    LONG = "long"
    SHORT = "short"
    EPHEMERAL = "ephemeral"


_DEFAULT_TTL_TICKS: Dict[RetentionTier, Optional[int]] = {
    RetentionTier.PERMANENT: None,  # never expires
    RetentionTier.LONG: 10_000,
    RetentionTier.SHORT: 1_000,
    RetentionTier.EPHEMERAL: 100,
}


@dataclass
class RetentionPolicy:
    """Defines how long each :class:`RetentionTier` keeps content alive.

    Parameters
    ----------
    tier_ttl_ticks:
        Mapping of tier → TTL in ticks.  ``None`` means never expires.
    default_tier:
        Tier applied when no explicit tier is given.
    """

    tier_ttl_ticks: Dict[RetentionTier, Optional[int]] = field(
        default_factory=lambda: dict(_DEFAULT_TTL_TICKS)
    )
    default_tier: RetentionTier = RetentionTier.SHORT

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_ttl(self, tier: RetentionTier) -> Optional[int]:
        """Return the TTL in ticks for *tier* (``None`` = infinite)."""
        return self.tier_ttl_ticks.get(tier, _DEFAULT_TTL_TICKS.get(tier))

    def is_permanent(self, tier: RetentionTier) -> bool:
        """True when the tier has no expiry."""
        return self.get_ttl(tier) is None

    def is_expired(self, tier: RetentionTier, age_ticks: int) -> bool:
        """True when *age_ticks* exceeds the TTL for *tier*.

        Permanent tiers never expire.
        """
        ttl = self.get_ttl(tier)
        if ttl is None:
            return False
        return age_ticks >= ttl

    def expires_at(self, tier: RetentionTier, stored_tick: int) -> Optional[int]:
        """Return the absolute tick at which this item expires, or None."""
        ttl = self.get_ttl(tier)
        if ttl is None:
            return None
        return stored_tick + ttl


@dataclass
class RetentionSchedule:
    """Tracks scheduled retention actions for a single snapshot.

    Attributes
    ----------
    snapshot_id:
        The snapshot this schedule entry applies to.
    tier:
        The retention tier assigned to this snapshot.
    stored_tick:
        The tick at which the snapshot was accepted into the vault.
    scheduled_purge_tick:
        Absolute tick at which purge should happen.  ``None`` for PERMANENT.
    purged:
        Set to True once the snapshot has been purged.
    """

    snapshot_id: int
    tier: RetentionTier
    stored_tick: int
    scheduled_purge_tick: Optional[int]
    purged: bool = False

    @classmethod
    def create(
        cls,
        snapshot_id: int,
        tier: RetentionTier,
        stored_tick: int,
        policy: RetentionPolicy,
    ) -> "RetentionSchedule":
        """Factory that computes :attr:`scheduled_purge_tick` from *policy*."""
        purge_tick = policy.expires_at(tier, stored_tick)
        return cls(
            snapshot_id=snapshot_id,
            tier=tier,
            stored_tick=stored_tick,
            scheduled_purge_tick=purge_tick,
        )

    def is_due(self, current_tick: int) -> bool:
        """True when it is time to purge this snapshot.

        Returns False for PERMANENT (no scheduled_purge_tick) and for already
        purged entries.
        """
        if self.purged:
            return False
        if self.scheduled_purge_tick is None:
            return False
        return current_tick >= self.scheduled_purge_tick

    def mark_purged(self) -> None:
        self.purged = True


class RetentionScheduler:
    """In-process registry of :class:`RetentionSchedule` entries."""

    def __init__(self, policy: Optional[RetentionPolicy] = None) -> None:
        self._policy = policy or RetentionPolicy()
        self._schedules: Dict[int, RetentionSchedule] = {}
        self._current_tick: int = 0

    def enqueue(
        self,
        snapshot_id: int,
        tier: RetentionTier,
        stored_tick: Optional[int] = None,
    ) -> RetentionSchedule:
        """Register a new retention schedule entry."""
        tick = stored_tick if stored_tick is not None else self._current_tick
        sched = RetentionSchedule.create(snapshot_id, tier, tick, self._policy)
        self._schedules[snapshot_id] = sched
        return sched

    def advance_tick(self, by: int = 1) -> None:
        self._current_tick += by

    @property
    def current_tick(self) -> int:
        return self._current_tick

    def due_for_purge(self) -> List[RetentionSchedule]:
        """Return all schedules that are due at the current tick."""
        return [s for s in self._schedules.values() if s.is_due(self._current_tick)]

    def mark_purged(self, snapshot_id: int) -> bool:
        sched = self._schedules.get(snapshot_id)
        if sched is None:
            return False
        sched.mark_purged()
        return True

    def get(self, snapshot_id: int) -> Optional[RetentionSchedule]:
        return self._schedules.get(snapshot_id)

    def remove(self, snapshot_id: int) -> bool:
        if snapshot_id in self._schedules:
            del self._schedules[snapshot_id]
            return True
        return False

    @property
    def size(self) -> int:
        return len(self._schedules)
