"""Tests for app/services/pipeline/ — Phase H."""

from __future__ import annotations

import pytest

from app.services.pipeline.stage_registry import StageDescriptor, StageRegistry
from app.services.pipeline.service_locator import ServiceBinding, ServiceLocator
from app.services.pipeline.circuit_breaker import BreakerState, CircuitBreaker
from app.services.pipeline.health_probe import HealthProbe, ProbeRecord, ProbeStatus
from app.services.pipeline.pipeline_metrics import PipelineMetrics
from app.services.pipeline.pipeline_runtime import PipelineRuntime

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _echo(payload):
    return dict(payload)


def _add_one(payload):
    return {k: v + 1 if isinstance(v, int) else v for k, v in payload.items()}


def _explode(payload):
    raise ValueError("stage exploded")


# ===========================================================================
# StageRegistry
# ===========================================================================


class TestStageRegistry:

    def test_register_and_has(self):
        reg = StageRegistry()
        reg.register("a", _echo)
        assert reg.has("a") is True

    def test_has_missing_returns_false(self):
        reg = StageRegistry()
        assert reg.has("x") is False

    def test_register_duplicate_raises(self):
        reg = StageRegistry()
        reg.register("a", _echo)
        with pytest.raises(ValueError):
            reg.register("a", _echo)

    def test_get_returns_descriptor(self):
        reg = StageRegistry()
        reg.register("a", _echo)
        d = reg.get("a")
        assert isinstance(d, StageDescriptor)
        assert d.name == "a"

    def test_get_missing_returns_none(self):
        reg = StageRegistry()
        assert reg.get("x") is None

    def test_get_fn_returns_callable(self):
        reg = StageRegistry()
        reg.register("a", _echo)
        assert reg.get_fn("a") is _echo

    def test_get_fn_missing_returns_none(self):
        reg = StageRegistry()
        assert reg.get_fn("x") is None

    def test_unregister_known_returns_true(self):
        reg = StageRegistry()
        reg.register("a", _echo)
        assert reg.unregister("a") is True
        assert reg.has("a") is False

    def test_unregister_unknown_returns_false(self):
        reg = StageRegistry()
        assert reg.unregister("x") is False

    def test_count(self):
        reg = StageRegistry()
        assert reg.count() == 0
        reg.register("a", _echo)
        assert reg.count() == 1

    def test_enable_disable(self):
        reg = StageRegistry()
        reg.register("a", _echo)
        assert reg.disable("a") is True
        assert reg.get("a").is_enabled() is False
        assert reg.enable("a") is True
        assert reg.get("a").is_enabled() is True

    def test_enable_unknown_returns_false(self):
        reg = StageRegistry()
        assert reg.enable("x") is False

    def test_disable_unknown_returns_false(self):
        reg = StageRegistry()
        assert reg.disable("x") is False

    def test_all_stages_sorted_by_priority_then_name(self):
        reg = StageRegistry()
        reg.register("b", _echo, priority=1)
        reg.register("a", _echo, priority=2)
        reg.register("c", _echo, priority=0)
        names = [d.name for d in reg.all_stages()]
        assert names == ["c", "b", "a"]

    def test_enabled_stages_filters_disabled(self):
        reg = StageRegistry()
        reg.register("a", _echo)
        reg.register("b", _echo)
        reg.disable("b")
        names = [d.name for d in reg.enabled_stages()]
        assert "a" in names
        assert "b" not in names

    def test_stages_with_tag(self):
        reg = StageRegistry()
        reg.register("a", _echo, tags={"x"})
        reg.register("b", _echo, tags={"y"})
        reg.register("c", _echo, tags={"x", "y"})
        tagged = reg.stages_with_tag("x")
        names = {d.name for d in tagged}
        assert names == {"a", "c"}

    def test_stage_names_sorted(self):
        reg = StageRegistry()
        reg.register("c", _echo)
        reg.register("a", _echo)
        assert reg.stage_names() == ["a", "c"]


# ===========================================================================
# ServiceLocator
# ===========================================================================


class TestServiceLocator:

    def test_register_and_is_registered(self):
        loc = ServiceLocator()
        loc.register("svc", object())
        assert loc.is_registered("svc") is True

    def test_is_registered_missing(self):
        loc = ServiceLocator()
        assert loc.is_registered("x") is False

    def test_register_duplicate_raises(self):
        loc = ServiceLocator()
        loc.register("svc", object())
        with pytest.raises(ValueError):
            loc.register("svc", object())

    def test_register_overwrite(self):
        loc = ServiceLocator()
        obj1, obj2 = object(), object()
        loc.register("svc", obj1)
        loc.register("svc", obj2, overwrite=True)
        assert loc.resolve("svc") is obj2

    def test_resolve_returns_instance(self):
        loc = ServiceLocator()
        obj = object()
        loc.register("svc", obj)
        assert loc.resolve("svc") is obj

    def test_resolve_missing_raises(self):
        loc = ServiceLocator()
        with pytest.raises(KeyError):
            loc.resolve("x")

    def test_try_resolve_returns_instance(self):
        loc = ServiceLocator()
        obj = object()
        loc.register("svc", obj)
        assert loc.try_resolve("svc") is obj

    def test_try_resolve_missing_returns_default(self):
        loc = ServiceLocator()
        sentinel = object()
        assert loc.try_resolve("x", default=sentinel) is sentinel

    def test_resolve_by_type(self):
        class MyService:
            pass

        loc = ServiceLocator()
        inst = MyService()
        loc.register("ms", inst)
        found = loc.resolve_by_type(MyService)
        assert found is inst

    def test_resolve_by_type_missing_raises(self):
        class MyService:
            pass

        loc = ServiceLocator()
        with pytest.raises(KeyError):
            loc.resolve_by_type(MyService)

    def test_unregister_known_returns_true(self):
        loc = ServiceLocator()
        loc.register("svc", object())
        assert loc.unregister("svc") is True
        assert loc.is_registered("svc") is False

    def test_unregister_unknown_returns_false(self):
        loc = ServiceLocator()
        assert loc.unregister("x") is False

    def test_with_tag(self):
        loc = ServiceLocator()
        loc.register("a", object(), tags={"alpha"})
        loc.register("b", object(), tags={"beta"})
        loc.register("c", object(), tags={"alpha", "beta"})
        tagged = loc.with_tag("alpha")
        interfaces = {b.interface for b in tagged}
        assert interfaces == {"a", "c"}

    def test_count_and_clear(self):
        loc = ServiceLocator()
        loc.register("a", object())
        loc.register("b", object())
        assert loc.count() == 2
        loc.clear()
        assert loc.count() == 0

    def test_registered_names_sorted(self):
        loc = ServiceLocator()
        loc.register("z", object())
        loc.register("a", object())
        assert loc.registered_names() == ["a", "z"]


# ===========================================================================
# CircuitBreaker
# ===========================================================================


class TestCircuitBreaker:

    def test_starts_closed(self):
        cb = CircuitBreaker()
        assert cb.state == BreakerState.CLOSED

    def test_allows_when_closed(self):
        cb = CircuitBreaker()
        assert cb.allow() is True

    def test_opens_at_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == BreakerState.OPEN

    def test_blocks_when_open(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()
        assert cb.allow() is False

    def test_ticks_to_half_open(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_ticks=3)
        cb.record_failure()
        for _ in range(3):
            cb.tick()
        assert cb.state == BreakerState.HALF_OPEN

    def test_half_open_allows_request(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_ticks=1)
        cb.record_failure()
        cb.tick()
        assert cb.state == BreakerState.HALF_OPEN
        assert cb.allow() is True

    def test_success_in_half_open_closes(self):
        cb = CircuitBreaker(
            failure_threshold=1, recovery_ticks=1, half_open_successes=1
        )
        cb.record_failure()
        cb.tick()
        cb.record_success()
        assert cb.state == BreakerState.CLOSED

    def test_failure_in_half_open_reopens(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_ticks=1)
        cb.record_failure()
        cb.tick()
        cb.record_failure()
        assert cb.state == BreakerState.OPEN

    def test_reset_to_closed(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()
        cb.reset()
        assert cb.state == BreakerState.CLOSED
        assert cb.failure_count == 0

    def test_failure_count_increments(self):
        cb = CircuitBreaker(failure_threshold=10)
        cb.record_failure()
        cb.record_failure()
        assert cb.failure_count == 2

    def test_success_resets_failure_count(self):
        cb = CircuitBreaker(failure_threshold=10)
        cb.record_failure()
        cb.record_success()
        assert cb.failure_count == 0

    def test_is_open_is_closed_is_half_open(self):
        cb = CircuitBreaker(failure_threshold=1, recovery_ticks=1)
        assert cb.is_closed
        cb.record_failure()
        assert cb.is_open
        cb.tick()
        assert cb.is_half_open

    def test_history_recorded(self):
        cb = CircuitBreaker(failure_threshold=10)
        cb.record_success()
        cb.record_failure()
        h = cb.history()
        assert h == ["ok", "fail"]

    def test_error_rate(self):
        cb = CircuitBreaker(failure_threshold=10)
        cb.record_success()
        cb.record_failure()
        cb.record_failure()
        assert abs(cb.error_rate() - 2 / 3) < 1e-9


# ===========================================================================
# HealthProbe
# ===========================================================================


class TestHealthProbe:

    def test_default_score_no_data(self):
        hp = HealthProbe()
        assert hp.health_score() == 1.0

    def test_record_healthy(self):
        hp = HealthProbe()
        hp.record(ProbeStatus.HEALTHY, tick=1)
        assert hp.health_score() == 1.0

    def test_record_unhealthy(self):
        hp = HealthProbe()
        hp.record(ProbeStatus.UNHEALTHY, tick=1)
        assert hp.health_score() == 0.0

    def test_window_trims_old_records(self):
        hp = HealthProbe(window_size=3)
        for i in range(5):
            hp.record(ProbeStatus.HEALTHY, tick=i)
        assert hp.window_count() == 3

    def test_history_returns_copy(self):
        hp = HealthProbe()
        hp.record(ProbeStatus.HEALTHY, tick=1)
        hist = hp.history()
        hist.clear()
        assert hp.window_count() == 1

    def test_current_status_healthy(self):
        hp = HealthProbe()
        for _ in range(9):
            hp.record(ProbeStatus.HEALTHY, tick=0)
        hp.record(ProbeStatus.UNHEALTHY, tick=0)
        assert hp.current_status() == ProbeStatus.HEALTHY  # 9/10 = 0.9 > 0.8

    def test_current_status_degraded(self):
        hp = HealthProbe()
        for _ in range(6):
            hp.record(ProbeStatus.HEALTHY, tick=0)
        for _ in range(4):
            hp.record(ProbeStatus.UNHEALTHY, tick=0)
        # 6/10 = 0.6 → DEGRADED
        assert hp.current_status() == ProbeStatus.DEGRADED

    def test_current_status_unhealthy(self):
        hp = HealthProbe()
        for _ in range(3):
            hp.record(ProbeStatus.HEALTHY, tick=0)
        for _ in range(7):
            hp.record(ProbeStatus.UNHEALTHY, tick=0)
        # 3/10 = 0.3 → UNHEALTHY
        assert hp.current_status() == ProbeStatus.UNHEALTHY

    def test_is_healthy_true(self):
        hp = HealthProbe()
        hp.record(ProbeStatus.HEALTHY, tick=0)
        assert hp.is_healthy() is True

    def test_is_healthy_false(self):
        hp = HealthProbe()
        hp.record(ProbeStatus.UNHEALTHY, tick=0)
        assert hp.is_healthy() is False

    def test_probe_record_detail(self):
        hp = HealthProbe()
        hp.record(ProbeStatus.DEGRADED, tick=5, detail="slow response")
        rec = hp.latest()
        assert rec.detail == "slow response"
        assert rec.tick == 5

    def test_clear(self):
        hp = HealthProbe()
        hp.record(ProbeStatus.HEALTHY, tick=0)
        hp.clear()
        assert hp.window_count() == 0


# ===========================================================================
# PipelineMetrics
# ===========================================================================


class TestPipelineMetrics:

    def test_execution_count_starts_zero(self):
        m = PipelineMetrics()
        assert m.execution_count("s") == 0

    def test_failure_count_starts_zero(self):
        m = PipelineMetrics()
        assert m.failure_count("s") == 0

    def test_record_execution_success(self):
        m = PipelineMetrics()
        m.record_execution("s", duration_ms=10.0, success=True)
        assert m.execution_count("s") == 1
        assert m.failure_count("s") == 0

    def test_record_execution_failure(self):
        m = PipelineMetrics()
        m.record_execution("s", duration_ms=10.0, success=False)
        assert m.failure_count("s") == 1

    def test_success_rate(self):
        m = PipelineMetrics()
        m.record_execution("s", success=True)
        m.record_execution("s", success=False)
        assert abs(m.success_rate("s") - 0.5) < 1e-9

    def test_success_rate_zero_when_no_execs(self):
        m = PipelineMetrics()
        assert m.success_rate("x") == 0.0

    def test_average_duration(self):
        m = PipelineMetrics()
        m.record_execution("s", duration_ms=10.0)
        m.record_execution("s", duration_ms=20.0)
        assert abs(m.average_duration("s") - 15.0) < 1e-9

    def test_average_duration_none_when_no_execs(self):
        m = PipelineMetrics()
        assert m.average_duration("x") is None

    def test_all_stage_names_sorted(self):
        m = PipelineMetrics()
        m.record_execution("z")
        m.record_execution("a")
        assert m.all_stage_names() == ["a", "z"]

    def test_reset_specific(self):
        m = PipelineMetrics()
        m.record_execution("s")
        m.reset("s")
        assert m.execution_count("s") == 0

    def test_reset_all(self):
        m = PipelineMetrics()
        m.record_execution("a")
        m.record_execution("b")
        m.reset_all()
        assert m.all_stage_names() == []

    def test_snapshot_keys(self):
        m = PipelineMetrics()
        m.record_execution("s", duration_ms=5.0, success=True)
        snap = m.snapshot()
        assert "s" in snap
        assert "executions" in snap["s"]
        assert snap["s"]["executions"] == 1


# ===========================================================================
# PipelineRuntime
# ===========================================================================


class TestPipelineRuntime:

    def _runtime_with(self, *stages):
        """stages = list of (name, fn) tuples."""
        reg = StageRegistry()
        for name, fn in stages:
            reg.register(name, fn)
        return PipelineRuntime(registry=reg)

    def test_run_executes_stage(self):
        rt = self._runtime_with(("echo", _echo))
        result = rt.run("echo", {"x": 1})
        assert result == {"x": 1}

    def test_run_unknown_stage_raises(self):
        rt = PipelineRuntime()
        with pytest.raises(KeyError):
            rt.run("nope", {})

    def test_run_records_metrics(self):
        rt = self._runtime_with(("echo", _echo))
        rt.run("echo", {})
        assert rt.metrics.execution_count("echo") == 1

    def test_run_failure_records_in_metrics(self):
        rt = self._runtime_with(("boom", _explode))
        with pytest.raises(ValueError):
            rt.run("boom", {})
        assert rt.metrics.failure_count("boom") == 1

    def test_run_sequence_chains_output(self):
        def double(p):
            return {"n": p["n"] * 2}

        def add_ten(p):
            return {"n": p["n"] + 10}

        reg = StageRegistry()
        reg.register("double", double)
        reg.register("add_ten", add_ten)
        rt = PipelineRuntime(registry=reg)
        result = rt.run_sequence(["double", "add_ten"], {"n": 5})
        assert result == {"n": 20}  # 5*2=10, 10+10=20

    def test_run_sequence_empty(self):
        rt = PipelineRuntime()
        payload = {"x": 99}
        result = rt.run_sequence([], dict(payload))
        assert result == payload

    def test_run_tagged_runs_matching_stages(self):
        reg = StageRegistry()
        reg.register("a", _echo, tags={"group"})
        reg.register("b", _echo, tags={"group"})
        reg.register("c", _echo, tags={"other"})
        rt = PipelineRuntime(registry=reg)
        results = rt.run_tagged("group", {"v": 1})
        assert len(results) == 2
        assert all(r == {"v": 1} for r in results)

    def test_run_tagged_skips_disabled(self):
        reg = StageRegistry()
        reg.register("a", _echo, tags={"t"})
        reg.register("b", _echo, tags={"t"})
        reg.disable("b")
        rt = PipelineRuntime(registry=reg)
        results = rt.run_tagged("t", {})
        assert len(results) == 1

    def test_circuit_breaker_blocks_open(self):
        cb = CircuitBreaker(failure_threshold=1)
        cb.record_failure()  # force OPEN
        reg = StageRegistry()
        reg.register("s", _echo)
        rt = PipelineRuntime(registry=reg)
        rt.add_circuit_breaker("s", cb)
        with pytest.raises(RuntimeError):
            rt.run("s", {})

    def test_circuit_breaker_passes_when_closed(self):
        cb = CircuitBreaker(failure_threshold=10)
        reg = StageRegistry()
        reg.register("s", _echo)
        rt = PipelineRuntime(registry=reg)
        rt.add_circuit_breaker("s", cb)
        result = rt.run("s", {"ok": True})
        assert result == {"ok": True}

    def test_circuit_breaker_updates_on_failure(self):
        cb = CircuitBreaker(failure_threshold=5)
        reg = StageRegistry()
        reg.register("boom", _explode)
        rt = PipelineRuntime(registry=reg)
        rt.add_circuit_breaker("boom", cb)
        with pytest.raises(ValueError):
            rt.run("boom", {})
        assert cb.failure_count == 1

    def test_status_dict_keys(self):
        reg = StageRegistry()
        reg.register("s", _echo)
        rt = PipelineRuntime(registry=reg)
        s = rt.status()
        assert "enabled_stage_count" in s
        assert "stage_names" in s
        assert "metrics" in s
        assert "circuit_breakers" in s

    def test_status_stage_count(self):
        reg = StageRegistry()
        reg.register("a", _echo)
        reg.register("b", _echo)
        rt = PipelineRuntime(registry=reg)
        assert rt.status()["enabled_stage_count"] == 2

    def test_get_circuit_breaker(self):
        cb = CircuitBreaker()
        rt = PipelineRuntime()
        rt.add_circuit_breaker("s", cb)
        assert rt.get_circuit_breaker("s") is cb
        assert rt.get_circuit_breaker("x") is None
