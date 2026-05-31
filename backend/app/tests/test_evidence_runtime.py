"""Tests for the Phase F evidence vault runtime package."""

from __future__ import annotations

import hashlib
import pytest

from app.evidence.runtime import (
    ContentAddress,
    ContentAddresser,
    IntegrityResult,
    IntegrityChecker,
    RetentionTier,
    RetentionPolicy,
    RetentionSchedule,
    SnapshotState,
    SnapshotLifecycle,
    VaultStat,
    VaultMetrics,
    VaultRuntimeConfig,
    VaultRuntime,
)
from app.evidence.runtime.retention_policy import RetentionScheduler
from app.evidence.runtime.snapshot_lifecycle import SnapshotTransitionError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ===========================================================================
# ContentAddress
# ===========================================================================


class TestContentAddress:
    def test_fields(self):
        addr = ContentAddress(hash_hex="a" * 64, size=100, mime="text/plain")
        assert addr.hash_hex == "a" * 64
        assert addr.size == 100
        assert addr.mime == "text/plain"

    def test_mime_optional(self):
        addr = ContentAddress(hash_hex="b" * 64, size=0)
        assert addr.mime is None

    def test_short_hash(self):
        addr = ContentAddress(hash_hex="abcdef" + "0" * 58, size=10)
        assert addr.short_hash(6) == "abcdef"

    def test_matches_same(self):
        a = ContentAddress(hash_hex="c" * 64, size=5)
        b = ContentAddress(hash_hex="c" * 64, size=999)  # size differs
        assert a.matches(b) is True

    def test_matches_different(self):
        a = ContentAddress(hash_hex="a" * 64, size=5)
        b = ContentAddress(hash_hex="b" * 64, size=5)
        assert a.matches(b) is False

    def test_str(self):
        addr = ContentAddress(hash_hex="d" * 64, size=42)
        result = str(addr)
        assert "sha256:" in result
        assert "42B" in result

    def test_frozen(self):
        addr = ContentAddress(hash_hex="e" * 64, size=1)
        with pytest.raises((AttributeError, TypeError)):
            addr.size = 999  # type: ignore[misc]


# ===========================================================================
# ContentAddresser
# ===========================================================================


class TestContentAddresser:
    def test_address_of_empty(self):
        ca = ContentAddresser()
        addr = ca.address_of(b"")
        assert addr.hash_hex == _sha256(b"")
        assert addr.size == 0

    def test_address_of_content(self):
        ca = ContentAddresser()
        data = b"hello world"
        addr = ca.address_of(data)
        assert addr.hash_hex == _sha256(data)
        assert addr.size == len(data)

    def test_address_of_mime(self):
        ca = ContentAddresser()
        addr = ca.address_of(b"data", mime="application/pdf")
        assert addr.mime == "application/pdf"

    def test_register_and_lookup(self):
        ca = ContentAddresser()
        addr = ca.address_of(b"test")
        ca.register(1, addr)
        assert ca.lookup(1) == addr

    def test_lookup_missing_returns_none(self):
        ca = ContentAddresser()
        assert ca.lookup(999) is None

    def test_has(self):
        ca = ContentAddresser()
        ca.register(5, ca.address_of(b"x"))
        assert ca.has(5) is True
        assert ca.has(6) is False

    def test_deregister(self):
        ca = ContentAddresser()
        ca.register(1, ca.address_of(b"x"))
        assert ca.deregister(1) is True
        assert ca.has(1) is False

    def test_deregister_missing(self):
        ca = ContentAddresser()
        assert ca.deregister(999) is False

    def test_registry_size(self):
        ca = ContentAddresser()
        for i in range(5):
            ca.register(i, ca.address_of(bytes([i])))
        assert ca.registry_size == 5

    def test_find_duplicates(self):
        ca = ContentAddresser()
        addr = ca.address_of(b"dup")
        ca.register(1, addr)
        ca.register(2, addr)
        ca.register(3, ca.address_of(b"unique"))
        dups = ca.find_duplicates()
        assert addr.hash_hex in dups
        assert set(dups[addr.hash_hex]) == {1, 2}

    def test_find_duplicates_empty(self):
        ca = ContentAddresser()
        assert ca.find_duplicates() == {}

    def test_clear(self):
        ca = ContentAddresser()
        for i in range(3):
            ca.register(i, ca.address_of(bytes([i])))
        removed = ca.clear()
        assert removed == 3
        assert ca.registry_size == 0

    def test_address_of_hex_valid(self):
        ca = ContentAddresser()
        h = "a" * 64
        addr = ca.address_of_hex(h, 50, "text/plain")
        assert addr.hash_hex == h
        assert addr.size == 50

    def test_address_of_hex_bad_length(self):
        ca = ContentAddresser()
        with pytest.raises(ValueError):
            ca.address_of_hex("tooshort", 0)


# ===========================================================================
# IntegrityResult
# ===========================================================================


class TestIntegrityResult:
    def test_ok(self):
        r = IntegrityResult(ok=True, expected_hash="aaa", actual_hash="aaa")
        assert r.ok is True
        assert r.is_tampered is False

    def test_fail(self):
        r = IntegrityResult(ok=False, expected_hash="aaa", actual_hash="bbb")
        assert r.ok is False
        assert r.is_tampered is True

    def test_mismatch_prefix(self):
        r = IntegrityResult(ok=False, expected_hash="a" * 64, actual_hash="b" * 64)
        prefix = r.mismatch_prefix
        assert "exp=" in prefix
        assert "got=" in prefix

    def test_snapshot_id_optional(self):
        r = IntegrityResult(ok=True, expected_hash="x", actual_hash="x")
        assert r.snapshot_id is None

    def test_str(self):
        r = IntegrityResult(
            ok=True, expected_hash="a" * 64, actual_hash="a" * 64, snapshot_id=7
        )
        assert "OK" in str(r)
        assert "sid=7" in str(r)


# ===========================================================================
# IntegrityChecker
# ===========================================================================


class TestIntegrityChecker:
    def test_check_passing(self):
        data = b"evidence"
        ic = IntegrityChecker()
        result = ic.check(data, _sha256(data))
        assert result.ok is True

    def test_check_failing(self):
        ic = IntegrityChecker()
        result = ic.check(b"tampered", _sha256(b"original"))
        assert result.ok is False

    def test_check_with_snapshot_id(self):
        ic = IntegrityChecker()
        data = b"data"
        result = ic.check(data, _sha256(data), snapshot_id=42)
        assert result.snapshot_id == 42

    def test_check_hex_ok(self):
        ic = IntegrityChecker()
        result = ic.check_hex("abc", "abc")
        assert result.ok is True

    def test_check_hex_fail(self):
        ic = IntegrityChecker()
        result = ic.check_hex("abc", "xyz")
        assert result.ok is False

    def test_check_batch_empty(self):
        ic = IntegrityChecker()
        assert ic.check_batch([]) == []

    def test_check_batch_all_ok(self):
        ic = IntegrityChecker()
        items = [(b"a", _sha256(b"a")), (b"b", _sha256(b"b"))]
        results = ic.check_batch(items)
        assert len(results) == 2
        assert ic.all_ok(results)

    def test_check_batch_partial_fail(self):
        ic = IntegrityChecker()
        items = [(b"ok", _sha256(b"ok")), (b"bad", "wrong_hash")]
        results = ic.check_batch(items)
        assert results[0].ok is True
        assert results[1].ok is False

    def test_check_batch_with_ids(self):
        ic = IntegrityChecker()
        items = [(1, b"content", _sha256(b"content"))]
        results = ic.check_batch_with_ids(items)
        assert results[0].snapshot_id == 1
        assert results[0].ok is True

    def test_all_ok_empty(self):
        ic = IntegrityChecker()
        assert ic.all_ok([]) is True

    def test_failures(self):
        ic = IntegrityChecker()
        items = [(b"ok", _sha256(b"ok")), (b"bad", "wrong")]
        results = ic.check_batch(items)
        fails = ic.failures(results)
        assert len(fails) == 1
        assert fails[0].ok is False

    def test_failure_count(self):
        ic = IntegrityChecker()
        items = [(b"a", "wrong"), (b"b", "wrong"), (b"c", _sha256(b"c"))]
        results = ic.check_batch(items)
        assert ic.failure_count(results) == 2


# ===========================================================================
# RetentionPolicy
# ===========================================================================


class TestRetentionPolicy:
    def test_permanent_has_no_ttl(self):
        rp = RetentionPolicy()
        assert rp.get_ttl(RetentionTier.PERMANENT) is None

    def test_ephemeral_has_ttl(self):
        rp = RetentionPolicy()
        ttl = rp.get_ttl(RetentionTier.EPHEMERAL)
        assert isinstance(ttl, int)
        assert ttl > 0

    def test_is_permanent(self):
        rp = RetentionPolicy()
        assert rp.is_permanent(RetentionTier.PERMANENT) is True
        assert rp.is_permanent(RetentionTier.EPHEMERAL) is False

    def test_is_expired_permanent_never(self):
        rp = RetentionPolicy()
        assert rp.is_expired(RetentionTier.PERMANENT, 999_999) is False

    def test_is_expired_ephemeral_yes(self):
        rp = RetentionPolicy()
        ttl = rp.get_ttl(RetentionTier.EPHEMERAL)
        assert rp.is_expired(RetentionTier.EPHEMERAL, ttl) is True
        assert rp.is_expired(RetentionTier.EPHEMERAL, ttl - 1) is False

    def test_expires_at_permanent(self):
        rp = RetentionPolicy()
        assert rp.expires_at(RetentionTier.PERMANENT, 50) is None

    def test_expires_at_short(self):
        rp = RetentionPolicy()
        ttl = rp.get_ttl(RetentionTier.SHORT)
        assert rp.expires_at(RetentionTier.SHORT, 0) == ttl

    def test_custom_ttl(self):
        rp = RetentionPolicy(tier_ttl_ticks={RetentionTier.EPHEMERAL: 5})
        assert rp.get_ttl(RetentionTier.EPHEMERAL) == 5
        assert rp.is_expired(RetentionTier.EPHEMERAL, 5) is True
        assert rp.is_expired(RetentionTier.EPHEMERAL, 4) is False


# ===========================================================================
# RetentionSchedule & RetentionScheduler
# ===========================================================================


class TestRetentionSchedule:
    def test_is_due_permanent(self):
        rp = RetentionPolicy()
        sched = RetentionSchedule.create(1, RetentionTier.PERMANENT, 0, rp)
        assert sched.is_due(999_999) is False

    def test_is_due_ephemeral(self):
        rp = RetentionPolicy(tier_ttl_ticks={RetentionTier.EPHEMERAL: 10})
        sched = RetentionSchedule.create(1, RetentionTier.EPHEMERAL, 0, rp)
        assert sched.is_due(9) is False
        assert sched.is_due(10) is True

    def test_mark_purged(self):
        rp = RetentionPolicy(tier_ttl_ticks={RetentionTier.EPHEMERAL: 1})
        sched = RetentionSchedule.create(1, RetentionTier.EPHEMERAL, 0, rp)
        assert sched.is_due(1) is True
        sched.mark_purged()
        assert sched.is_due(1) is False


class TestRetentionScheduler:
    def test_enqueue_and_get(self):
        rs = RetentionScheduler()
        sched = rs.enqueue(1, RetentionTier.SHORT)
        assert rs.get(1) == sched

    def test_advance_tick(self):
        rs = RetentionScheduler()
        rs.advance_tick(5)
        assert rs.current_tick == 5

    def test_due_for_purge(self):
        rp = RetentionPolicy(tier_ttl_ticks={RetentionTier.EPHEMERAL: 3})
        rs = RetentionScheduler(policy=rp)
        rs.enqueue(1, RetentionTier.EPHEMERAL, stored_tick=0)
        rs.advance_tick(2)
        assert rs.due_for_purge() == []
        rs.advance_tick(1)
        due = rs.due_for_purge()
        assert len(due) == 1
        assert due[0].snapshot_id == 1

    def test_mark_purged(self):
        rp = RetentionPolicy(tier_ttl_ticks={RetentionTier.EPHEMERAL: 1})
        rs = RetentionScheduler(policy=rp)
        rs.enqueue(1, RetentionTier.EPHEMERAL, stored_tick=0)
        rs.advance_tick(1)
        assert rs.mark_purged(1) is True
        assert rs.due_for_purge() == []

    def test_remove(self):
        rs = RetentionScheduler()
        rs.enqueue(1, RetentionTier.SHORT)
        assert rs.remove(1) is True
        assert rs.get(1) is None

    def test_size(self):
        rs = RetentionScheduler()
        rs.enqueue(1, RetentionTier.SHORT)
        rs.enqueue(2, RetentionTier.LONG)
        assert rs.size == 2


# ===========================================================================
# SnapshotLifecycle
# ===========================================================================


class TestSnapshotLifecycle:
    def _make(self):
        sl = SnapshotLifecycle()
        sl.register(1)
        return sl

    def test_initial_state(self):
        sl = self._make()
        assert sl.state_of(1) == SnapshotState.PENDING

    def test_unregistered_returns_none(self):
        sl = SnapshotLifecycle()
        assert sl.state_of(999) is None

    def test_store(self):
        sl = self._make()
        sl.store(1)
        assert sl.state_of(1) == SnapshotState.STORED

    def test_verify_after_store(self):
        sl = self._make()
        sl.store(1)
        sl.verify(1)
        assert sl.state_of(1) == SnapshotState.VERIFIED

    def test_expire_from_stored(self):
        sl = self._make()
        sl.store(1)
        sl.expire(1)
        assert sl.state_of(1) == SnapshotState.EXPIRED

    def test_expire_from_verified(self):
        sl = self._make()
        sl.store(1)
        sl.verify(1)
        sl.expire(1)
        assert sl.state_of(1) == SnapshotState.EXPIRED

    def test_purge_after_expire(self):
        sl = self._make()
        sl.store(1)
        sl.expire(1)
        sl.purge(1)
        assert sl.state_of(1) == SnapshotState.PURGED

    def test_invalid_transition(self):
        sl = self._make()
        with pytest.raises(SnapshotTransitionError):
            sl.verify(1)  # PENDING → VERIFIED is not allowed

    def test_purged_is_terminal(self):
        sl = self._make()
        sl.store(1)
        sl.expire(1)
        sl.purge(1)
        with pytest.raises(SnapshotTransitionError):
            sl.expire(1)

    def test_snapshots_by_state(self):
        sl = SnapshotLifecycle()
        for sid in range(1, 4):
            sl.register(sid)
            sl.store(sid)
        sl.verify(2)
        assert sl.snapshots_by_state(SnapshotState.STORED) == [1, 3]
        assert sl.snapshots_by_state(SnapshotState.VERIFIED) == [2]

    def test_history(self):
        sl = self._make()
        sl.store(1)
        sl.verify(1)
        history = sl.history_for(1)
        assert len(history) == 2
        assert history[0][0] == SnapshotState.PENDING
        assert history[1][0] == SnapshotState.STORED

    def test_allowed_next_states(self):
        sl = self._make()
        allowed = sl.allowed_next_states(1)
        assert SnapshotState.STORED in allowed

    def test_re_register_ignored(self):
        sl = SnapshotLifecycle()
        sl.register(1)
        sl.store(1)
        sl.register(1)  # should not reset state
        assert sl.state_of(1) == SnapshotState.STORED

    def test_total_registered(self):
        sl = SnapshotLifecycle()
        for i in range(3):
            sl.register(i)
        assert sl.total_registered == 3


# ===========================================================================
# VaultMetrics
# ===========================================================================


class TestVaultMetrics:
    def test_initial_zero(self):
        vm = VaultMetrics()
        for stat in VaultStat:
            assert vm.get(stat) == 0

    def test_increment(self):
        vm = VaultMetrics()
        vm.increment(VaultStat.SNAPSHOTS_STORED, 3)
        assert vm.get(VaultStat.SNAPSHOTS_STORED) == 3

    def test_increment_default_one(self):
        vm = VaultMetrics()
        vm.increment(VaultStat.INTEGRITY_CHECKS)
        assert vm.get(VaultStat.INTEGRITY_CHECKS) == 1

    def test_increment_negative_raises(self):
        vm = VaultMetrics()
        with pytest.raises(ValueError):
            vm.increment(VaultStat.SNAPSHOTS_STORED, -1)

    def test_reset_single(self):
        vm = VaultMetrics()
        vm.increment(VaultStat.INTEGRITY_FAILURES, 5)
        vm.reset(VaultStat.INTEGRITY_FAILURES)
        assert vm.get(VaultStat.INTEGRITY_FAILURES) == 0

    def test_reset_all(self):
        vm = VaultMetrics()
        for stat in VaultStat:
            vm.increment(stat, 1)
        vm.reset()
        assert vm.total_events == 0

    def test_snapshot(self):
        vm = VaultMetrics()
        vm.increment(VaultStat.SNAPSHOTS_STORED, 2)
        snap = vm.snapshot()
        assert snap["snapshots_stored"] == 2

    def test_total_events(self):
        vm = VaultMetrics()
        vm.increment(VaultStat.SNAPSHOTS_STORED, 4)
        vm.increment(VaultStat.INTEGRITY_CHECKS, 6)
        assert vm.total_events == 10

    def test_top_n(self):
        vm = VaultMetrics()
        vm.increment(VaultStat.SNAPSHOTS_STORED, 10)
        vm.increment(VaultStat.INTEGRITY_CHECKS, 7)
        vm.increment(VaultStat.SNAPSHOTS_VERIFIED, 3)
        top = vm.top_n(2)
        assert top[0] == ("snapshots_stored", 10)
        assert top[1] == ("integrity_checks", 7)

    def test_merge(self):
        vm1 = VaultMetrics()
        vm2 = VaultMetrics()
        vm1.increment(VaultStat.SNAPSHOTS_STORED, 3)
        vm2.increment(VaultStat.SNAPSHOTS_STORED, 2)
        vm2.increment(VaultStat.INTEGRITY_FAILURES, 1)
        vm1.merge(vm2)
        assert vm1.get(VaultStat.SNAPSHOTS_STORED) == 5
        assert vm1.get(VaultStat.INTEGRITY_FAILURES) == 1


# ===========================================================================
# VaultRuntime
# ===========================================================================


class TestVaultRuntime:
    def test_store_snapshot_returns_address(self):
        vr = VaultRuntime()
        data = b"evidence content"
        addr = vr.store_snapshot(1, data)
        assert isinstance(addr, ContentAddress)
        assert addr.hash_hex == _sha256(data)

    def test_store_registers_lifecycle(self):
        vr = VaultRuntime()
        vr.store_snapshot(1, b"data")
        assert vr.snapshot_state(1) == SnapshotState.STORED

    def test_verify_snapshot_ok(self):
        vr = VaultRuntime()
        data = b"evidence"
        vr.store_snapshot(1, data)
        result = vr.verify_snapshot(1, data, _sha256(data))
        assert result.ok is True
        assert vr.snapshot_state(1) == SnapshotState.VERIFIED

    def test_verify_snapshot_tampered(self):
        vr = VaultRuntime()
        data = b"original"
        vr.store_snapshot(1, data)
        result = vr.verify_snapshot(1, b"tampered", _sha256(data))
        assert result.ok is False
        assert vr.snapshot_state(1) == SnapshotState.STORED  # not advanced

    def test_check_integrity_standalone(self):
        vr = VaultRuntime()
        data = b"standalone"
        result = vr.check_integrity(data, _sha256(data))
        assert result.ok is True

    def test_expire_snapshot(self):
        vr = VaultRuntime()
        vr.store_snapshot(1, b"x")
        vr.expire_snapshot(1)
        assert vr.snapshot_state(1) == SnapshotState.EXPIRED

    def test_purge_snapshot(self):
        vr = VaultRuntime()
        vr.store_snapshot(1, b"x")
        vr.expire_snapshot(1)
        vr.purge_snapshot(1)
        assert vr.snapshot_state(1) == SnapshotState.PURGED

    def test_advance_tick_auto_expires(self):
        rp = RetentionPolicy(
            tier_ttl_ticks={
                RetentionTier.EPHEMERAL: 5,
                RetentionTier.SHORT: 1_000,
                RetentionTier.LONG: 10_000,
                RetentionTier.PERMANENT: None,
            }
        )
        cfg = VaultRuntimeConfig(
            retention_policy=rp, default_tier=RetentionTier.EPHEMERAL
        )
        vr = VaultRuntime(cfg)
        vr.store_snapshot(1, b"doc1")
        expired = vr.advance_tick(5)
        assert 1 in expired
        assert vr.snapshot_state(1) == SnapshotState.EXPIRED

    def test_advance_tick_not_yet_due(self):
        rp = RetentionPolicy(
            tier_ttl_ticks={
                RetentionTier.EPHEMERAL: 10,
                RetentionTier.SHORT: 1_000,
                RetentionTier.LONG: 10_000,
                RetentionTier.PERMANENT: None,
            }
        )
        cfg = VaultRuntimeConfig(
            retention_policy=rp, default_tier=RetentionTier.EPHEMERAL
        )
        vr = VaultRuntime(cfg)
        vr.store_snapshot(1, b"doc1")
        expired = vr.advance_tick(5)
        assert expired == []
        assert vr.snapshot_state(1) == SnapshotState.STORED

    def test_purge_expired_bulk(self):
        rp = RetentionPolicy(
            tier_ttl_ticks={
                RetentionTier.EPHEMERAL: 1,
                RetentionTier.SHORT: 1_000,
                RetentionTier.LONG: 10_000,
                RetentionTier.PERMANENT: None,
            }
        )
        cfg = VaultRuntimeConfig(
            retention_policy=rp, default_tier=RetentionTier.EPHEMERAL
        )
        vr = VaultRuntime(cfg)
        for sid in [1, 2, 3]:
            vr.store_snapshot(sid, bytes([sid]))
        vr.advance_tick(1)
        purged = vr.purge_expired()
        assert set(purged) == {1, 2, 3}
        for sid in [1, 2, 3]:
            assert vr.snapshot_state(sid) == SnapshotState.PURGED

    def test_metrics_snapshot_keys(self):
        vr = VaultRuntime()
        vr.store_snapshot(1, b"data")
        ms = vr.metrics_snapshot()
        assert "counters" in ms
        assert "lifecycle" in ms
        assert "retention" in ms
        assert "total_events" in ms

    def test_metrics_counts_store(self):
        vr = VaultRuntime()
        vr.store_snapshot(1, b"a")
        vr.store_snapshot(2, b"b")
        ms = vr.metrics_snapshot()
        assert ms["counters"]["snapshots_stored"] == 2

    def test_metrics_counts_integrity_failure(self):
        vr = VaultRuntime()
        vr.store_snapshot(1, b"x")
        vr.verify_snapshot(1, b"tampered", _sha256(b"x"))
        ms = vr.metrics_snapshot()
        assert ms["counters"]["integrity_failures"] == 1

    def test_compute_address_no_snapshot(self):
        vr = VaultRuntime()
        addr = vr.compute_address(b"raw", mime="text/plain")
        assert addr.hash_hex == _sha256(b"raw")
        assert addr.mime == "text/plain"

    def test_top_stats(self):
        vr = VaultRuntime()
        for i in range(5):
            vr.store_snapshot(i, bytes([i]))
        top = vr.top_stats(3)
        assert len(top) == 3
        assert top[0][1] >= top[1][1]  # sorted descending

    def test_check_integrity_batch(self):
        vr = VaultRuntime()
        items = []
        for i in range(3):
            data = bytes([i])
            sid = i + 1
            vr.store_snapshot(sid, data)
            items.append((sid, data, _sha256(data)))
        results = vr.check_integrity_batch(items)
        assert all(r.ok for r in results)

    def test_snapshot_state_unregistered(self):
        vr = VaultRuntime()
        assert vr.snapshot_state(999) is None

    def test_default_config(self):
        vr = VaultRuntime()
        cfg = vr._config
        assert isinstance(cfg, VaultRuntimeConfig)
        assert cfg.max_integrity_batch == 100
