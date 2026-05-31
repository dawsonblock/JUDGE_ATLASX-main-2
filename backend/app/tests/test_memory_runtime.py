"""Tests for the Phase-E memory runtime package (~90 tests)."""

from __future__ import annotations

import pytest

from app.memory.runtime.claim_lifecycle import (
    ClaimStatus,
    ClaimTransition,
    LifecyclePolicy,
)
from app.memory.runtime.state_machine import MemoryStateMachine, StateMachineError
from app.memory.runtime.diff_engine import ClaimDiff, DiffEngine, DiffKind, DiffResult
from app.memory.runtime.cache_policy import (
    CacheEntry,
    CachePolicy,
    ClaimCache,
    EvictionStrategy,
)
from app.memory.runtime.rebuild_scheduler import (
    RebuildSchedule,
    RebuildScheduler,
    RebuildTrigger,
)
from app.memory.runtime.memory_metrics import MemoryMetricStat, MemoryMetrics
from app.memory.runtime.memory_runtime import MemoryRuntime, MemoryRuntimeConfig

# ===========================================================================
# TestClaimStatus
# ===========================================================================


class TestClaimStatus:
    def test_all_values_present(self):
        values = {s.value for s in ClaimStatus}
        assert {"draft", "active", "stale", "invalidated", "archived"} == values

    def test_str_equality(self):
        assert ClaimStatus.ACTIVE == "active"
        assert ClaimStatus.DRAFT == "draft"


# ===========================================================================
# TestLifecyclePolicy
# ===========================================================================


class TestLifecyclePolicy:
    def test_default_stale_threshold(self):
        p = LifecyclePolicy()
        assert not p.should_go_stale(2)
        assert p.should_go_stale(3)
        assert p.should_go_stale(10)

    def test_custom_stale_threshold(self):
        p = LifecyclePolicy(stale_after_rebuilds=1)
        assert not p.should_go_stale(0)
        assert p.should_go_stale(1)

    def test_archive_threshold(self):
        p = LifecyclePolicy(archive_after_invalidated=5)
        assert not p.should_archive(4)
        assert p.should_archive(5)

    def test_hard_reasons(self):
        p = LifecyclePolicy()
        assert p.is_hard_invalidation("manual_reject")
        assert p.is_hard_invalidation("source_rejected")
        assert p.is_hard_invalidation("privacy_violation")
        assert not p.is_hard_invalidation("routine_rebuild")

    def test_reactivation_blocked(self):
        p = LifecyclePolicy(allow_reactivation=False)
        allowed = p.allowed_transitions(ClaimStatus.STALE)
        assert ClaimStatus.ACTIVE not in allowed

    def test_reactivation_allowed_by_default(self):
        p = LifecyclePolicy()
        allowed = p.allowed_transitions(ClaimStatus.STALE)
        assert ClaimStatus.ACTIVE in allowed


# ===========================================================================
# TestClaimTransition
# ===========================================================================


class TestClaimTransition:
    def test_valid_transition(self):
        tx = ClaimTransition(
            from_status=ClaimStatus.DRAFT,
            to_status=ClaimStatus.ACTIVE,
            reason="ok",
            claim_key="k1",
        )
        assert tx.is_valid()

    def test_invalid_transition(self):
        tx = ClaimTransition(
            from_status=ClaimStatus.ARCHIVED,
            to_status=ClaimStatus.ACTIVE,
            reason="bad",
            claim_key="k1",
        )
        assert not tx.is_valid()


# ===========================================================================
# TestMemoryStateMachine
# ===========================================================================


class TestMemoryStateMachine:
    def test_register_and_initial_status(self):
        sm = MemoryStateMachine()
        sm.register("k1")
        assert sm.status_of("k1") == ClaimStatus.DRAFT

    def test_register_duplicate_raises(self):
        sm = MemoryStateMachine()
        sm.register("k1")
        with pytest.raises(ValueError, match="already registered"):
            sm.register("k1")

    def test_register_or_get_idempotent(self):
        sm = MemoryStateMachine()
        s1 = sm.register_or_get("k1")
        s2 = sm.register_or_get("k1")
        assert s1 == s2 == ClaimStatus.DRAFT

    def test_activate(self):
        sm = MemoryStateMachine()
        sm.register("k1")
        sm.activate("k1")
        assert sm.status_of("k1") == ClaimStatus.ACTIVE

    def test_invalidate(self):
        sm = MemoryStateMachine()
        sm.register("k1")
        sm.activate("k1")
        sm.invalidate("k1", reason="test")
        assert sm.status_of("k1") == ClaimStatus.INVALIDATED

    def test_illegal_transition_raises(self):
        sm = MemoryStateMachine()
        sm.register("k1")
        # DRAFT → STALE is not allowed
        with pytest.raises(StateMachineError):
            sm.transition("k1", ClaimStatus.STALE)

    def test_unknown_claim_raises_key_error(self):
        sm = MemoryStateMachine()
        with pytest.raises(KeyError):
            sm.status_of("nope")

    def test_claims_by_status(self):
        sm = MemoryStateMachine()
        sm.register("a")
        sm.register("b")
        sm.activate("a")
        active = sm.claims_by_status(ClaimStatus.ACTIVE)
        draft = sm.claims_by_status(ClaimStatus.DRAFT)
        assert "a" in active
        assert "b" in draft

    def test_history_records_transitions(self):
        sm = MemoryStateMachine()
        sm.register("k1")
        sm.activate("k1")
        history = sm.history_for("k1")
        assert len(history) == 1
        assert history[0].to_status == ClaimStatus.ACTIVE

    def test_advance_rebuild_cycle_auto_stale(self):
        policy = LifecyclePolicy(stale_after_rebuilds=2)
        sm = MemoryStateMachine(policy=policy)
        sm.register("k1", ClaimStatus.ACTIVE)
        sm.advance_rebuild_cycle()  # rebuilds_since_touch = 1
        assert sm.status_of("k1") == ClaimStatus.ACTIVE
        sm.advance_rebuild_cycle()  # rebuild count = 2 → stale
        assert sm.status_of("k1") == ClaimStatus.STALE

    def test_advance_rebuild_cycle_auto_archive(self):
        policy = LifecyclePolicy(archive_after_invalidated=2)
        sm = MemoryStateMachine(policy=policy)
        sm.register("k1", ClaimStatus.INVALIDATED)
        # Seed the counter so first advance reaches threshold
        sm._records["k1"].rebuilds_since_invalidation = 1
        autos = sm.advance_rebuild_cycle()
        assert sm.status_of("k1") == ClaimStatus.ARCHIVED
        assert len(autos) == 1

    def test_claim_count(self):
        sm = MemoryStateMachine()
        assert sm.claim_count == 0
        sm.register("a")
        sm.register("b")
        assert sm.claim_count == 2

    def test_all_transitions(self):
        sm = MemoryStateMachine()
        sm.register("k1")
        sm.activate("k1")
        sm.invalidate("k1")
        assert len(sm.all_transitions) == 2


# ===========================================================================
# TestDiffEngine
# ===========================================================================


def _claim(key: str, text: str = "text") -> dict:
    return {"claim_key": key, "normalized_text": text}


class TestDiffEngine:
    def test_empty_vs_empty(self):
        de = DiffEngine()
        r = de.diff([], [])
        assert not r.has_changes
        assert r.total_count == 0

    def test_all_added(self):
        de = DiffEngine()
        r = de.diff([], [_claim("a"), _claim("b")])
        assert r.added == frozenset({"a", "b"})
        assert not r.removed
        assert r.has_changes

    def test_all_removed(self):
        de = DiffEngine()
        r = de.diff([_claim("a"), _claim("b")], [])
        assert r.removed == frozenset({"a", "b"})
        assert r.has_changes

    def test_modified(self):
        de = DiffEngine()
        r = de.diff([_claim("a", "old")], [_claim("a", "new")])
        assert r.modified == frozenset({"a"})
        assert not r.added
        assert not r.removed

    def test_unchanged(self):
        de = DiffEngine()
        r = de.diff([_claim("a")], [_claim("a")])
        assert r.unchanged == frozenset({"a"})
        assert not r.has_changes

    def test_mixed(self):
        de = DiffEngine()
        old = [_claim("a"), _claim("b", "v1"), _claim("c")]
        new = [_claim("b", "v2"), _claim("c"), _claim("d")]
        r = de.diff(old, new)
        assert "a" in r.removed
        assert "b" in r.modified
        assert "c" in r.unchanged
        assert "d" in r.added

    def test_summary_totals(self):
        de = DiffEngine()
        old = [_claim("a"), _claim("b")]
        new = [_claim("b", "changed"), _claim("c")]
        r = de.diff(old, new)
        s = r.summary()
        assert s["added"] == 1
        assert s["removed"] == 1
        assert s["modified"] == 1
        assert s["total"] == s["added"] + s["removed"] + s["modified"] + s["unchanged"]

    def test_change_count(self):
        de = DiffEngine()
        r = de.diff([_claim("a")], [_claim("b")])
        assert r.change_count == 2  # 1 removed + 1 added

    def test_key_set_diff(self):
        de = DiffEngine()
        old = frozenset({"a", "b", "c"})
        new = frozenset({"b", "c", "d"})
        result = de.key_set_diff(old, new)
        assert result["added"] == frozenset({"d"})
        assert result["removed"] == frozenset({"a"})
        assert result["common"] == frozenset({"b", "c"})

    def test_entries_contain_all_kinds(self):
        de = DiffEngine()
        old = [_claim("a"), _claim("b", "v1")]
        new = [_claim("b", "v2"), _claim("c")]
        r = de.diff(old, new)
        kinds = {e.kind for e in r.entries}
        assert DiffKind.ADDED in kinds
        assert DiffKind.REMOVED in kinds
        assert DiffKind.MODIFIED in kinds

    def test_is_structural_change(self):
        assert ClaimDiff("k", DiffKind.ADDED).is_structural_change()
        assert ClaimDiff("k", DiffKind.REMOVED).is_structural_change()
        assert not ClaimDiff("k", DiffKind.MODIFIED).is_structural_change()
        assert not ClaimDiff("k", DiffKind.UNCHANGED).is_structural_change()


# ===========================================================================
# TestCachePolicy
# ===========================================================================


class TestCachePolicy:
    def test_ttl_enabled(self):
        p = CachePolicy(ttl_ticks=10)
        assert p.is_ttl_enabled()

    def test_ttl_disabled_zero(self):
        p = CachePolicy(ttl_ticks=0)
        assert not p.is_ttl_enabled()

    def test_ttl_disabled_none(self):
        p = CachePolicy(ttl_ticks=None)
        assert not p.is_ttl_enabled()


# ===========================================================================
# TestCacheEntry
# ===========================================================================


class TestCacheEntry:
    def test_age(self):
        entry = CacheEntry(key="k", value=42, inserted_tick=5, last_accessed_tick=5)
        assert entry.age(10) == 5

    def test_is_expired(self):
        entry = CacheEntry(key="k", value=42, inserted_tick=0, last_accessed_tick=0)
        assert not entry.is_expired(4, ttl_ticks=5)
        assert entry.is_expired(5, ttl_ticks=5)


# ===========================================================================
# TestClaimCache
# ===========================================================================


class TestClaimCache:
    def test_put_and_get(self):
        c = ClaimCache()
        c.put("k1", {"data": 1})
        assert c.get("k1") == {"data": 1}

    def test_miss_returns_none(self):
        c = ClaimCache()
        assert c.get("nope") is None

    def test_hit_rate(self):
        c = ClaimCache()
        c.put("k1", "v")
        c.get("k1")  # hit
        c.get("nope")  # miss
        assert c.hit_rate == 0.5

    def test_ttl_expiry(self):
        policy = CachePolicy(ttl_ticks=3, max_entries=100)
        c = ClaimCache(policy)
        c.put("k1", "value")
        c.advance_tick(3)
        assert c.get("k1") is None  # expired

    def test_ttl_not_expired_yet(self):
        policy = CachePolicy(ttl_ticks=5, max_entries=100)
        c = ClaimCache(policy)
        c.put("k1", "value")
        c.advance_tick(4)
        assert c.get("k1") == "value"

    def test_eviction_lru(self):
        policy = CachePolicy(
            max_entries=2, ttl_ticks=None, eviction_strategy=EvictionStrategy.LRU
        )
        c = ClaimCache(policy)
        c.put("a", 1)  # inserted at tick=0
        c.advance_tick()  # tick=1
        c.put("b", 2)  # inserted at tick=1
        c.advance_tick()  # tick=2
        c.get("a")  # a last_accessed=2, b last_accessed=1 → b is LRU
        c.put("c", 3)  # evict b
        assert c.get("b") is None
        assert c.get("a") == 1
        assert c.get("c") == 3

    def test_eviction_fifo(self):
        policy = CachePolicy(
            max_entries=2, ttl_ticks=None, eviction_strategy=EvictionStrategy.FIFO
        )
        c = ClaimCache(policy)
        c.put("a", 1)
        c.advance_tick()
        c.put("b", 2)
        c.put("c", 3)  # evict "a" (oldest)
        assert c.get("a") is None
        assert c.get("b") == 2

    def test_explicit_evict(self):
        c = ClaimCache()
        c.put("k1", "v")
        assert c.evict("k1")
        assert c.get("k1") is None

    def test_evict_absent_returns_false(self):
        c = ClaimCache()
        assert not c.evict("nope")

    def test_purge_expired(self):
        policy = CachePolicy(ttl_ticks=2, max_entries=100)
        c = ClaimCache(policy)
        c.put("a", 1)
        c.put("b", 2)
        c.advance_tick(2)
        removed = c.purge_expired()
        assert removed == 2
        assert c.size == 0

    def test_purge_no_ttl_does_nothing(self):
        policy = CachePolicy(ttl_ticks=None, max_entries=100)
        c = ClaimCache(policy)
        c.put("a", 1)
        assert c.purge_expired() == 0
        assert c.size == 1

    def test_clear(self):
        c = ClaimCache()
        c.put("a", 1)
        c.put("b", 2)
        removed = c.clear()
        assert removed == 2
        assert c.size == 0

    def test_update_existing(self):
        c = ClaimCache()
        c.put("k1", "v1")
        c.put("k1", "v2")
        assert c.get("k1") == "v2"
        assert c.size == 1


# ===========================================================================
# TestRebuildScheduler
# ===========================================================================


class TestRebuildScheduler:
    def test_schedule_and_next_ready(self):
        s = RebuildScheduler()
        s.schedule(42, RebuildTrigger.MANUAL)
        entry = s.next_ready()
        assert entry is not None
        assert entry.entity_id == 42

    def test_pending_count(self):
        s = RebuildScheduler()
        s.schedule(1)
        s.schedule(2)
        assert s.pending_count == 2

    def test_next_ready_respects_run_after_tick(self):
        s = RebuildScheduler()
        s.schedule(1, delay_ticks=5)
        assert s.next_ready() is None
        s.advance_tick(5)
        entry = s.next_ready()
        assert entry is not None
        assert entry.entity_id == 1

    def test_priority_ordering(self):
        s = RebuildScheduler()
        s.schedule(1, priority=10)
        s.schedule(2, priority=1)
        s.schedule(3, priority=5)
        first = s.next_ready()
        assert first is not None and first.entity_id == 2  # lowest priority number

    def test_complete(self):
        s = RebuildScheduler()
        s.schedule(1)
        s.next_ready()  # move to in-flight
        assert s.complete(1)
        assert s.completed_count == 1
        assert s.in_flight_count == 0

    def test_fail_requeues_with_backoff(self):
        s = RebuildScheduler(max_retries=2, retry_delay_ticks=3)
        s.schedule(1)
        s.next_ready()
        retried = s.fail(1, "network")
        assert retried is not None
        assert s.pending_count == 1
        assert retried.attempt == 1

    def test_fail_exhausts_retries(self):
        s = RebuildScheduler(max_retries=1, retry_delay_ticks=0)
        s.schedule(1)
        s.next_ready()
        s.fail(1)  # attempt 1 → requeued with no delay
        s.next_ready()  # back in-flight (retry_delay_ticks=0 → immediately ready)
        result = s.fail(1)  # attempt 2 → exhausted
        assert result is None
        assert s.failed_count == 1

    def test_drain_ready(self):
        s = RebuildScheduler()
        s.schedule(1)
        s.schedule(2)
        s.schedule(3)
        entries = s.drain_ready()
        assert len(entries) == 3
        assert s.pending_count == 0
        assert s.in_flight_count == 3

    def test_schedule_many(self):
        s = RebuildScheduler()
        schedules = s.schedule_many([1, 2, 3], RebuildTrigger.SOURCE_UPDATED)
        assert len(schedules) == 3
        assert s.pending_count == 3

    def test_is_pending_and_in_flight(self):
        s = RebuildScheduler()
        s.schedule(99)
        assert s.is_pending(99)
        assert not s.is_in_flight(99)
        s.next_ready()
        assert not s.is_pending(99)
        assert s.is_in_flight(99)

    def test_duplicate_schedule_promotes_priority(self):
        s = RebuildScheduler()
        s.schedule(5, priority=10)
        s.schedule(5, priority=2)  # promote
        entry = s.next_ready()
        assert entry is not None and entry.priority == 2

    def test_stats(self):
        s = RebuildScheduler()
        s.schedule(1)
        stats = s.stats()
        assert stats["pending"] == 1
        assert stats["in_flight"] == 0


# ===========================================================================
# TestMemoryMetrics
# ===========================================================================


class TestMemoryMetrics:
    def test_increment_and_get(self):
        m = MemoryMetrics()
        m.increment(MemoryMetricStat.CLAIMS_ACTIVATED, 3)
        assert m.get(MemoryMetricStat.CLAIMS_ACTIVATED) == 3

    def test_default_zero(self):
        m = MemoryMetrics()
        assert m.get(MemoryMetricStat.REBUILDS_FAILED) == 0

    def test_reset_single(self):
        m = MemoryMetrics()
        m.increment(MemoryMetricStat.CACHE_HITS, 5)
        m.reset(MemoryMetricStat.CACHE_HITS)
        assert m.get(MemoryMetricStat.CACHE_HITS) == 0

    def test_reset_all(self):
        m = MemoryMetrics()
        m.increment(MemoryMetricStat.DIFF_RUNS, 10)
        m.increment(MemoryMetricStat.CACHE_MISSES, 3)
        m.reset()
        assert m.total_events == 0

    def test_snapshot(self):
        m = MemoryMetrics()
        m.increment(MemoryMetricStat.REBUILDS_SCHEDULED, 2)
        snap = m.snapshot()
        assert snap["rebuilds_scheduled"] == 2

    def test_merge(self):
        m1 = MemoryMetrics()
        m2 = MemoryMetrics()
        m1.increment(MemoryMetricStat.DIFF_ADDED, 4)
        m2.increment(MemoryMetricStat.DIFF_ADDED, 6)
        m1.merge(m2)
        assert m1.get(MemoryMetricStat.DIFF_ADDED) == 10

    def test_top_n(self):
        m = MemoryMetrics()
        m.increment(MemoryMetricStat.CACHE_HITS, 100)
        m.increment(MemoryMetricStat.CACHE_MISSES, 20)
        m.increment(MemoryMetricStat.DIFF_RUNS, 5)
        top = m.top_n(2)
        assert top[0][0] == "cache_hits"
        assert top[1][0] == "cache_misses"

    def test_total_events(self):
        m = MemoryMetrics()
        m.increment(MemoryMetricStat.CLAIMS_ACTIVATED, 3)
        m.increment(MemoryMetricStat.CLAIMS_INVALIDATED, 2)
        assert m.total_events == 5


# ===========================================================================
# TestMemoryRuntime (integration)
# ===========================================================================


class TestMemoryRuntime:
    def test_default_construction(self):
        rt = MemoryRuntime()
        assert rt.state_machine.claim_count == 0

    def test_register_and_activate(self):
        rt = MemoryRuntime()
        rt.register_claim("k1")
        rt.activate_claim("k1")
        assert rt.claim_status("k1") == ClaimStatus.ACTIVE
        assert rt.metrics.get(MemoryMetricStat.CLAIMS_ACTIVATED) == 1

    def test_invalidate_records_metric(self):
        rt = MemoryRuntime()
        rt.register_claim("k1")
        rt.activate_claim("k1")
        rt.invalidate_claim("k1", reason="test")
        assert rt.metrics.get(MemoryMetricStat.CLAIMS_INVALIDATED) == 1

    def test_active_and_stale_claims(self):
        rt = MemoryRuntime()
        rt.register_claim("a")
        rt.activate_claim("a")
        rt.register_claim("b", ClaimStatus.STALE)
        assert "a" in rt.active_claims()
        assert "b" in rt.stale_claims()

    def test_advance_rebuild_cycle_triggers_stale(self):
        config = MemoryRuntimeConfig(
            lifecycle_policy=LifecyclePolicy(stale_after_rebuilds=1)
        )
        rt = MemoryRuntime(config)
        rt.register_claim("k1", ClaimStatus.ACTIVE)
        count = rt.advance_rebuild_cycle()
        assert count == 1
        assert rt.claim_status("k1") == ClaimStatus.STALE

    def test_diff_claims_updates_metrics(self):
        rt = MemoryRuntime()
        old = [_claim("a"), _claim("b")]
        new = [_claim("b", "changed"), _claim("c")]
        result = rt.diff_claims(old, new)
        assert result.has_changes
        assert rt.metrics.get(MemoryMetricStat.DIFF_RUNS) == 1
        assert rt.metrics.get(MemoryMetricStat.DIFF_ADDED) == 1
        assert rt.metrics.get(MemoryMetricStat.DIFF_REMOVED) == 1
        assert rt.metrics.get(MemoryMetricStat.DIFF_MODIFIED) == 1

    def test_cache_put_get_miss(self):
        rt = MemoryRuntime()
        rt.cache_put("k1", {"x": 1})
        assert rt.cache_get("k1") == {"x": 1}
        assert rt.cache_get("nope") is None
        assert rt.metrics.get(MemoryMetricStat.CACHE_HITS) == 1
        assert rt.metrics.get(MemoryMetricStat.CACHE_MISSES) == 1

    def test_cache_evict_records_metric(self):
        rt = MemoryRuntime()
        rt.cache_put("k1", "v")
        assert rt.cache_evict("k1")
        assert rt.metrics.get(MemoryMetricStat.CACHE_EVICTIONS) == 1

    def test_schedule_and_complete_rebuild(self):
        rt = MemoryRuntime()
        rt.schedule_rebuild(42, RebuildTrigger.MANUAL)
        assert rt.metrics.get(MemoryMetricStat.REBUILDS_SCHEDULED) == 1
        nxt = rt.next_rebuild()
        assert nxt is not None and nxt.entity_id == 42
        rt.complete_rebuild(42)
        assert rt.metrics.get(MemoryMetricStat.REBUILDS_COMPLETED) == 1

    def test_fail_rebuild_records_metric_when_exhausted(self):
        config = MemoryRuntimeConfig(max_retries=0)
        rt = MemoryRuntime(config)
        rt.schedule_rebuild(1)
        rt.next_rebuild()
        retried = rt.fail_rebuild(1)
        assert not retried
        assert rt.metrics.get(MemoryMetricStat.REBUILDS_FAILED) == 1

    def test_fail_rebuild_requeues(self):
        config = MemoryRuntimeConfig(max_retries=2)
        rt = MemoryRuntime(config)
        rt.schedule_rebuild(1)
        rt.next_rebuild()
        retried = rt.fail_rebuild(1)
        assert retried  # re-queued

    def test_metrics_snapshot_structure(self):
        rt = MemoryRuntime()
        snap = rt.metrics_snapshot()
        assert "counters" in snap
        assert "scheduler" in snap
        assert "cache" in snap
        assert "state_machine" in snap

    def test_register_claim_with_custom_status(self):
        rt = MemoryRuntime()
        rt.register_claim("k1", ClaimStatus.ACTIVE)
        assert rt.claim_status("k1") == ClaimStatus.ACTIVE

    def test_full_lifecycle_round_trip(self):
        """Simulate a realistic rebuild cycle."""
        config = MemoryRuntimeConfig(
            lifecycle_policy=LifecyclePolicy(
                stale_after_rebuilds=2, archive_after_invalidated=2
            )
        )
        rt = MemoryRuntime(config)

        # Register some claims
        for i in range(3):
            rt.register_claim(f"claim_{i}")
            rt.activate_claim(f"claim_{i}")

        # Invalidate one explicitly
        rt.invalidate_claim("claim_2", reason="privacy_violation")

        # Two rebuild cycles
        rt.advance_rebuild_cycle()
        rt.advance_rebuild_cycle()

        # claim_0 and claim_1 should have gone stale (stale_after_rebuilds=2)
        assert rt.claim_status("claim_0") == ClaimStatus.STALE
        assert rt.claim_status("claim_1") == ClaimStatus.STALE

        # claim_2 should be archived (archive_after_invalidated=2)
        assert rt.claim_status("claim_2") == ClaimStatus.ARCHIVED

        # Check metrics recorded the transitions
        assert rt.metrics.get(MemoryMetricStat.CLAIMS_STALED) == 2
        assert rt.metrics.get(MemoryMetricStat.CLAIMS_ARCHIVED) == 1
