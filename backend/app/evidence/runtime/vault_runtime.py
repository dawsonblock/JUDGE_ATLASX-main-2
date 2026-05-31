"""Vault runtime — orchestrator façade for the evidence vault subsystem."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from app.evidence.runtime.content_addresser import ContentAddress, ContentAddresser
from app.evidence.runtime.integrity_checker import IntegrityChecker, IntegrityResult
from app.evidence.runtime.retention_policy import (
    RetentionPolicy,
    RetentionScheduler,
    RetentionTier,
)
from app.evidence.runtime.snapshot_lifecycle import (
    SnapshotLifecycle,
    SnapshotState,
    SnapshotTransitionError,
)
from app.evidence.runtime.vault_metrics import VaultMetrics, VaultStat


@dataclass
class VaultRuntimeConfig:
    """Configuration bundle for :class:`VaultRuntime`.

    Attributes
    ----------
    retention_policy:
        TTL rules per tier.
    default_tier:
        Tier applied when :meth:`VaultRuntime.store_snapshot` is called
        without an explicit tier.
    max_integrity_batch:
        Maximum items accepted by :meth:`VaultRuntime.check_integrity_batch`.
    """

    retention_policy: RetentionPolicy = field(default_factory=RetentionPolicy)
    default_tier: RetentionTier = RetentionTier.SHORT
    max_integrity_batch: int = 100


class VaultRuntime:
    """Coordinates content addressing, integrity, retention, and lifecycle.

    This class is the single entry-point for the evidence vault runtime and
    acts as a thin orchestration layer over the individual modules.
    """

    def __init__(self, config: Optional[VaultRuntimeConfig] = None) -> None:
        self._config = config or VaultRuntimeConfig()
        self._addresser = ContentAddresser()
        self._checker = IntegrityChecker()
        self._lifecycle = SnapshotLifecycle()
        self._scheduler = RetentionScheduler(policy=self._config.retention_policy)
        self._metrics = VaultMetrics()

    # ------------------------------------------------------------------
    # Content addressing
    # ------------------------------------------------------------------

    def compute_address(
        self, content: bytes, mime: str | None = None
    ) -> ContentAddress:
        """Compute the content address for *content* (no snapshot required)."""
        self._metrics.increment(VaultStat.ADDRESSES_COMPUTED)
        return self._addresser.address_of(content, mime=mime)

    # ------------------------------------------------------------------
    # Snapshot storage
    # ------------------------------------------------------------------

    def store_snapshot(
        self,
        snapshot_id: int,
        content: bytes,
        mime: str | None = None,
        tier: Optional[RetentionTier] = None,
    ) -> ContentAddress:
        """Register a snapshot, compute its address, and schedule retention.

        Parameters
        ----------
        snapshot_id:
            Numeric identifier (matches DB primary key).
        content:
            Raw bytes of the evidence blob.
        mime:
            Optional MIME hint.
        tier:
            Retention tier; defaults to :attr:`VaultRuntimeConfig.default_tier`.

        Returns
        -------
        ContentAddress
            The computed address that was registered.
        """
        effective_tier = tier if tier is not None else self._config.default_tier

        # Content address
        self._metrics.increment(VaultStat.ADDRESSES_COMPUTED)
        address = self._addresser.address_of(content, mime=mime)
        self._addresser.register(snapshot_id, address)

        # Register and advance snapshot lifecycle to STORED
        self._lifecycle.register(snapshot_id)
        self._lifecycle.store(snapshot_id, "stored by vault")

        # Schedule retention
        self._scheduler.enqueue(
            snapshot_id, effective_tier, self._scheduler.current_tick
        )

        self._metrics.increment(VaultStat.SNAPSHOTS_STORED)
        return address

    # ------------------------------------------------------------------
    # Integrity
    # ------------------------------------------------------------------

    def verify_snapshot(
        self,
        snapshot_id: int,
        content: bytes,
        expected_hash: str,
    ) -> IntegrityResult:
        """Verify *content* against *expected_hash* and advance lifecycle.

        On success transitions the snapshot to VERIFIED.
        On failure increments INTEGRITY_FAILURES and does *not* advance state.
        """
        result = self._checker.check(content, expected_hash, snapshot_id=snapshot_id)
        self._metrics.increment(VaultStat.INTEGRITY_CHECKS)

        if result.ok:
            state = self._lifecycle.state_of(snapshot_id)
            if state == SnapshotState.STORED:
                self._lifecycle.verify(snapshot_id, "integrity verified")
                self._metrics.increment(VaultStat.SNAPSHOTS_VERIFIED)
        else:
            self._metrics.increment(VaultStat.INTEGRITY_FAILURES)

        return result

    def check_integrity(self, content: bytes, expected_hash: str) -> IntegrityResult:
        """Standalone integrity check (no snapshot registration required)."""
        self._metrics.increment(VaultStat.INTEGRITY_CHECKS)
        result = self._checker.check(content, expected_hash)
        if not result.ok:
            self._metrics.increment(VaultStat.INTEGRITY_FAILURES)
        return result

    def check_integrity_batch(
        self,
        items: List[tuple],
    ) -> List[IntegrityResult]:
        """Check a batch of (snapshot_id, content, expected_hash) tuples.

        Capped at :attr:`VaultRuntimeConfig.max_integrity_batch` items.
        """
        cap = self._config.max_integrity_batch
        items = items[:cap]
        results = []
        for sid, content, expected in items:
            results.append(self.verify_snapshot(sid, content, expected))
        return results

    # ------------------------------------------------------------------
    # Lifecycle transitions
    # ------------------------------------------------------------------

    def expire_snapshot(self, snapshot_id: int, reason: str = "expired") -> None:
        """Mark *snapshot_id* as EXPIRED."""
        self._lifecycle.expire(snapshot_id, reason)
        self._metrics.increment(VaultStat.SNAPSHOTS_EXPIRED)

    def purge_snapshot(self, snapshot_id: int, reason: str = "purged") -> None:
        """Mark *snapshot_id* as PURGED and update retention scheduler."""
        self._lifecycle.purge(snapshot_id, reason)
        self._scheduler.mark_purged(snapshot_id)
        self._metrics.increment(VaultStat.SNAPSHOTS_PURGED)

    def snapshot_state(self, snapshot_id: int) -> Optional[SnapshotState]:
        """Return the current lifecycle state of *snapshot_id*."""
        return self._lifecycle.state_of(snapshot_id)

    # ------------------------------------------------------------------
    # Tick / retention
    # ------------------------------------------------------------------

    def advance_tick(self, by: int = 1) -> List[int]:
        """Advance the internal clock and auto-expire due snapshots.

        Returns
        -------
        list[int]
            Snapshot IDs that were expired this tick.
        """
        self._scheduler.advance_tick(by)
        expired_ids = []
        for sched in self._scheduler.due_for_purge():
            state = self._lifecycle.state_of(sched.snapshot_id)
            if state in (SnapshotState.STORED, SnapshotState.VERIFIED):
                try:
                    self._lifecycle.expire(sched.snapshot_id, "retention TTL")
                    self._metrics.increment(VaultStat.SNAPSHOTS_EXPIRED)
                    self._metrics.increment(VaultStat.RETENTION_EXPIRATIONS)
                    expired_ids.append(sched.snapshot_id)
                except SnapshotTransitionError:
                    pass
        return expired_ids

    def purge_expired(self) -> List[int]:
        """Purge all snapshots currently in EXPIRED state.

        Returns
        -------
        list[int]
            Snapshot IDs that were purged.
        """
        expired = self._lifecycle.snapshots_by_state(SnapshotState.EXPIRED)
        purged = []
        for sid in expired:
            try:
                self.purge_snapshot(sid, "bulk purge")
                self._metrics.increment(VaultStat.RETENTION_PURGES)
                purged.append(sid)
            except Exception:
                pass
        return purged

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def metrics_snapshot(self) -> Dict[str, object]:
        """Return a point-in-time view of all vault metrics."""
        counters = self._metrics.snapshot()
        return {
            "counters": counters,
            "total_events": self._metrics.total_events,
            "registry_size": self._addresser.registry_size,
            "lifecycle": {
                "total_registered": self._lifecycle.total_registered,
                "by_state": {
                    s.value: len(self._lifecycle.snapshots_by_state(s))
                    for s in SnapshotState
                },
            },
            "retention": {
                "current_tick": self._scheduler.current_tick,
                "scheduled": self._scheduler.size,
            },
        }

    def top_stats(self, n: int = 5) -> List[tuple]:
        return self._metrics.top_n(n)
