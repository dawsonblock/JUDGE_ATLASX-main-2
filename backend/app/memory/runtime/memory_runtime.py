"""Memory runtime — top-level orchestrator for Phase E.

Wires together the state machine, diff engine, cache, rebuild scheduler,
and metrics into one coherent facade.  Entirely in-process and DB-free;
all I/O is deferred to the caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Sequence

from app.memory.runtime.cache_policy import CachePolicy, ClaimCache, EvictionStrategy
from app.memory.runtime.claim_lifecycle import ClaimStatus, LifecyclePolicy
from app.memory.runtime.diff_engine import DiffEngine, DiffResult
from app.memory.runtime.memory_metrics import MemoryMetricStat, MemoryMetrics
from app.memory.runtime.rebuild_scheduler import RebuildScheduler, RebuildTrigger
from app.memory.runtime.state_machine import MemoryStateMachine, StateMachineError


@dataclass
class MemoryRuntimeConfig:
    """Configuration bundle for :class:`MemoryRuntime`.

    Attributes
    ----------
    lifecycle_policy:
        Rules governing automatic claim state transitions.
    cache_policy:
        Size, TTL and eviction strategy for the claim cache.
    max_retries:
        Max rebuild retries per entity.
    retry_delay_ticks:
        Tick delay multiplier between retries.
    """

    lifecycle_policy: LifecyclePolicy = field(default_factory=LifecyclePolicy)
    cache_policy: CachePolicy = field(
        default_factory=lambda: CachePolicy(max_entries=512, ttl_ticks=120)
    )
    max_retries: int = 3
    retry_delay_ticks: int = 2


class MemoryRuntime:
    """Single-entry-point façade over the memory runtime subsystem.

    Responsibilities
    ----------------
    - Maintain lifecycle state for individual claims (via
      :class:`MemoryStateMachine`).
    - Compute set-level diffs between rebuild snapshots (via
      :class:`DiffEngine`).
    - Provide an LRU/FIFO claim payload cache (via :class:`ClaimCache`).
    - Schedule and dispatch entity rebuilds (via
      :class:`RebuildScheduler`).
    - Emit aggregate metrics (via :class:`MemoryMetrics`).

    Design constraints
    ------------------
    * Deterministic — no random or time-dependent behaviour.
    * No DB calls — all persistence is the caller's job.
    * No LLM calls.
    """

    def __init__(self, config: MemoryRuntimeConfig | None = None) -> None:
        self.config = config or MemoryRuntimeConfig()
        self.state_machine = MemoryStateMachine(policy=self.config.lifecycle_policy)
        self.diff_engine = DiffEngine()
        self.cache = ClaimCache(policy=self.config.cache_policy)
        self.scheduler = RebuildScheduler(
            max_retries=self.config.max_retries,
            retry_delay_ticks=self.config.retry_delay_ticks,
        )
        self.metrics = MemoryMetrics()

    # ------------------------------------------------------------------
    # Claim lifecycle
    # ------------------------------------------------------------------

    def register_claim(
        self, claim_key: str, initial_status: ClaimStatus = ClaimStatus.DRAFT
    ) -> None:
        """Register *claim_key* in the state machine."""
        self.state_machine.register(claim_key, initial_status)

    def activate_claim(self, claim_key: str) -> None:
        """Activate *claim_key* and record metric."""
        self.state_machine.activate(claim_key)
        self.metrics.increment(MemoryMetricStat.CLAIMS_ACTIVATED)

    def invalidate_claim(self, claim_key: str, reason: str = "invalidated") -> None:
        """Invalidate *claim_key* and record metric."""
        self.state_machine.invalidate(claim_key, reason)
        self.metrics.increment(MemoryMetricStat.CLAIMS_INVALIDATED)

    def claim_status(self, claim_key: str) -> ClaimStatus:
        return self.state_machine.status_of(claim_key)

    def active_claims(self) -> List[str]:
        return self.state_machine.claims_by_status(ClaimStatus.ACTIVE)

    def stale_claims(self) -> List[str]:
        return self.state_machine.claims_by_status(ClaimStatus.STALE)

    # ------------------------------------------------------------------
    # Rebuild cycle
    # ------------------------------------------------------------------

    def advance_rebuild_cycle(self) -> int:
        """Tick the state machine and cache; return count of auto-transitions."""
        auto_txs = self.state_machine.advance_rebuild_cycle()
        self.cache.advance_tick()
        self.scheduler.advance_tick()
        staled = sum(1 for tx in auto_txs if tx.to_status == ClaimStatus.STALE)
        archived = sum(1 for tx in auto_txs if tx.to_status == ClaimStatus.ARCHIVED)
        if staled:
            self.metrics.increment(MemoryMetricStat.CLAIMS_STALED, staled)
        if archived:
            self.metrics.increment(MemoryMetricStat.CLAIMS_ARCHIVED, archived)
        return len(auto_txs)

    # ------------------------------------------------------------------
    # Diff
    # ------------------------------------------------------------------

    def diff_claims(
        self,
        old_claims: Sequence[dict],
        new_claims: Sequence[dict],
    ) -> DiffResult:
        """Compare two claim snapshots and update diff metrics."""
        result = self.diff_engine.diff(old_claims, new_claims)
        self.metrics.increment(MemoryMetricStat.DIFF_RUNS)
        self.metrics.increment(MemoryMetricStat.DIFF_ADDED, len(result.added))
        self.metrics.increment(MemoryMetricStat.DIFF_REMOVED, len(result.removed))
        self.metrics.increment(MemoryMetricStat.DIFF_MODIFIED, len(result.modified))
        return result

    # ------------------------------------------------------------------
    # Cache
    # ------------------------------------------------------------------

    def cache_put(self, claim_key: str, payload: Any) -> None:
        self.cache.put(claim_key, payload)

    def cache_get(self, claim_key: str) -> Any | None:
        value = self.cache.get(claim_key)
        if value is not None:
            self.metrics.increment(MemoryMetricStat.CACHE_HITS)
        else:
            self.metrics.increment(MemoryMetricStat.CACHE_MISSES)
        return value

    def cache_evict(self, claim_key: str) -> bool:
        evicted = self.cache.evict(claim_key)
        if evicted:
            self.metrics.increment(MemoryMetricStat.CACHE_EVICTIONS)
        return evicted

    # ------------------------------------------------------------------
    # Rebuild scheduling
    # ------------------------------------------------------------------

    def schedule_rebuild(
        self,
        entity_id: int,
        trigger: RebuildTrigger = RebuildTrigger.SCHEDULED,
        priority: int = 5,
    ) -> None:
        """Request a rebuild for *entity_id*."""
        self.scheduler.schedule(entity_id, trigger, priority)
        self.metrics.increment(MemoryMetricStat.REBUILDS_SCHEDULED)

    def next_rebuild(self):
        """Return the next ready rebuild schedule entry, or None."""
        return self.scheduler.next_ready()

    def complete_rebuild(self, entity_id: int) -> None:
        self.scheduler.complete(entity_id)
        self.metrics.increment(MemoryMetricStat.REBUILDS_COMPLETED)

    def fail_rebuild(self, entity_id: int, reason: str = "") -> bool:
        """Mark rebuild failed; returns True if re-queued for retry."""
        retried = self.scheduler.fail(entity_id, reason)
        if retried is None:
            self.metrics.increment(MemoryMetricStat.REBUILDS_FAILED)
        return retried is not None

    # ------------------------------------------------------------------
    # Metrics / diagnostics
    # ------------------------------------------------------------------

    def metrics_snapshot(self) -> dict[str, Any]:
        return {
            "counters": self.metrics.snapshot(),
            "scheduler": self.scheduler.stats(),
            "cache": {
                "size": self.cache.size,
                "hits": self.cache.hits,
                "misses": self.cache.misses,
                "hit_rate": round(self.cache.hit_rate, 4),
            },
            "state_machine": {
                "total_claims": self.state_machine.claim_count,
                "active": len(self.active_claims()),
                "stale": len(self.stale_claims()),
            },
        }
