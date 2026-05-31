"""Tests for the Phase-D workers runtime package (~87 tests)."""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from app.workers.deadlock_detector import DeadlockDetector, InFlightRecord
from app.workers.job_queue import JobEnvelope, JobQueue, Priority
from app.workers.job_registry import JobRegistry, JobSpec
from app.workers.job_result import JobResult, JobStatus, ResultStore
from app.workers.pipeline_coordinator import (
    PipelineCoordinator,
    PipelineStep,
)
from app.workers.retry_policy import (
    BackoffStrategy,
    FAST_RETRY_POLICY,
    IMMEDIATE_POLICY,
    RetryPolicy,
    SLOW_RETRY_POLICY,
    STANDARD_POLICY,
)
from app.workers.task_router import RouteEntry, TaskRouter
from app.workers.worker_health import WorkerBeat, WorkerHealthMonitor, WorkerState
from app.workers.worker_metrics import WorkerMetrics
from app.workers.workers_runtime import WorkersRuntime, WorkersRuntimeConfig

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _noop(**kwargs):  # noqa: ANN001
    return "ok"


def _boom(**kwargs):  # noqa: ANN001
    raise RuntimeError("bang")


def _runtime_with_handler(job_name: str = "test_job") -> WorkersRuntime:
    cfg = WorkersRuntimeConfig(default_retry_policy=IMMEDIATE_POLICY)
    rt = WorkersRuntime(cfg)
    rt.router.register(job_name, _noop)
    return rt


# ===========================================================================
# TestJobRegistry
# ===========================================================================


class TestJobRegistry:
    def test_register_and_get(self):
        reg = JobRegistry()
        reg.register("my_job", _noop)
        spec = reg.get("my_job")
        assert spec is not None
        assert spec.name == "my_job"
        assert spec.handler is _noop

    def test_get_missing_returns_none(self):
        reg = JobRegistry()
        assert reg.get("nope") is None

    def test_require_missing_raises(self):
        reg = JobRegistry()
        with pytest.raises(KeyError):
            reg.require("nope")

    def test_require_found_returns_spec(self):
        reg = JobRegistry()
        reg.register("j", _noop)
        assert reg.require("j").name == "j"

    def test_list_names(self):
        reg = JobRegistry()
        reg.register("a", _noop)
        reg.register("b", _noop)
        names = reg.list_names()
        assert "a" in names and "b" in names

    def test_len(self):
        reg = JobRegistry()
        assert len(reg) == 0
        reg.register("x", _noop)
        assert len(reg) == 1

    def test_contains(self):
        reg = JobRegistry()
        reg.register("x", _noop)
        assert "x" in reg
        assert "y" not in reg

    def test_overwrite(self):
        reg = JobRegistry()
        reg.register("x", _noop)
        reg.register("x", _boom)
        assert reg.require("x").handler is _boom


# ===========================================================================
# TestJobQueue
# ===========================================================================


class TestJobQueue:
    def test_empty_dequeue_returns_none(self):
        q = JobQueue()
        assert q.dequeue() is None

    def test_enqueue_returns_job_id(self):
        q = JobQueue()
        jid = q.enqueue("j", {})
        assert isinstance(jid, str) and len(jid) > 0

    def test_len(self):
        q = JobQueue()
        assert len(q) == 0
        q.enqueue("j", {})
        assert len(q) == 1

    def test_is_empty(self):
        q = JobQueue()
        assert q.is_empty()
        q.enqueue("j", {})
        assert not q.is_empty()

    def test_priority_ordering(self):
        q = JobQueue()
        q.enqueue("low", {}, priority=Priority.LOW)
        q.enqueue("critical", {}, priority=Priority.CRITICAL)
        q.enqueue("normal", {}, priority=Priority.NORMAL)
        first = q.dequeue()
        assert first.priority == Priority.CRITICAL

    def test_fifo_within_same_priority(self):
        q = JobQueue()
        q.enqueue("first", {}, priority=Priority.NORMAL)
        time.sleep(0.01)
        q.enqueue("second", {}, priority=Priority.NORMAL)
        first = q.dequeue()
        assert first.job_name == "first"

    def test_peek_does_not_remove(self):
        q = JobQueue()
        q.enqueue("j", {})
        q.peek()
        assert len(q) == 1

    def test_clear(self):
        q = JobQueue()
        q.enqueue("j", {})
        q.clear()
        assert len(q) == 0

    def test_duplicate_job_id_raises(self):
        q = JobQueue()
        q.enqueue("j", {}, job_id="same-id")
        with pytest.raises(ValueError):
            q.enqueue("j2", {}, job_id="same-id")

    def test_custom_job_id_preserved(self):
        q = JobQueue()
        q.enqueue("j", {}, job_id="my-custom-id")
        env = q.dequeue()
        assert env.job_id == "my-custom-id"


# ===========================================================================
# TestJobResult
# ===========================================================================


class TestJobResult:
    def _make_result(self, status=JobStatus.SUCCESS, **kw):
        defaults = dict(
            job_id="x",
            job_name="j",
            status=status,
            attempt=1,
            started_at=0.0,
            finished_at=1.0,
        )
        defaults.update(kw)
        return JobResult(**defaults)

    def test_succeeded_true(self):
        r = self._make_result(status=JobStatus.SUCCESS)
        assert r.succeeded
        assert not r.failed

    def test_failed_true(self):
        r = self._make_result(status=JobStatus.DEAD)
        assert r.failed
        assert not r.succeeded

    def test_duration_seconds(self):
        r = self._make_result(started_at=0.0, finished_at=2.5)
        assert r.duration_seconds == pytest.approx(2.5)

    def test_result_store_record_and_get_latest(self):
        store = ResultStore()
        r = self._make_result(job_id="abc", job_name="my_job")
        store.record(r)
        assert store.get_latest("abc") is r

    def test_result_store_get_history(self):
        store = ResultStore()
        r1 = self._make_result(job_id="abc")
        r2 = self._make_result(job_id="abc", attempt=2)
        store.record(r1)
        store.record(r2)
        assert len(store.get_history("abc")) == 2

    def test_result_store_list_by_status(self):
        store = ResultStore()
        store.record(self._make_result(job_id="a", status=JobStatus.SUCCESS))
        store.record(self._make_result(job_id="b", status=JobStatus.DEAD))
        successes = store.list_by_status(JobStatus.SUCCESS)
        assert all(r.status == JobStatus.SUCCESS for r in successes)

    def test_result_store_recent(self):
        store = ResultStore()
        for i in range(5):
            store.record(self._make_result(job_id=str(i)))
        assert len(store.recent(3)) == 3

    def test_result_store_eviction_at_max_size(self):
        store = ResultStore(max_size=3)
        for i in range(5):
            store.record(self._make_result(job_id=str(i)))
        assert len(store) <= 3


# ===========================================================================
# TestWorkerHealthMonitor
# ===========================================================================


class TestWorkerHealthMonitor:
    def test_heartbeat_recorded(self):
        mon = WorkerHealthMonitor()
        mon.heartbeat("w1", WorkerState.IDLE)
        beat = mon.get_beat("w1")
        assert beat is not None
        assert beat.state == WorkerState.IDLE

    def test_is_alive_fresh(self):
        mon = WorkerHealthMonitor(stale_seconds=60.0)
        mon.heartbeat("w1", WorkerState.IDLE)
        assert mon.is_alive("w1")

    def test_is_alive_stale(self):
        mon = WorkerHealthMonitor(stale_seconds=0.01)
        mon.heartbeat("w1", WorkerState.IDLE)
        time.sleep(0.05)
        assert not mon.is_alive("w1")

    def test_unknown_worker_is_not_alive(self):
        mon = WorkerHealthMonitor()
        assert not mon.is_alive("ghost")

    def test_active_workers(self):
        mon = WorkerHealthMonitor(stale_seconds=60.0)
        mon.heartbeat("w1", WorkerState.IDLE)
        mon.heartbeat("w2", WorkerState.BUSY)
        assert set(b.worker_id for b in mon.active_workers()) == {"w1", "w2"}

    def test_stale_workers(self):
        mon = WorkerHealthMonitor(stale_seconds=0.01)
        mon.heartbeat("w1", WorkerState.IDLE)
        time.sleep(0.05)
        assert any(b.worker_id == "w1" for b in mon.stale_workers())

    def test_deregister(self):
        mon = WorkerHealthMonitor()
        mon.heartbeat("w1", WorkerState.IDLE)
        mon.deregister("w1")
        assert mon.get_beat("w1") is None


# ===========================================================================
# TestRetryPolicy
# ===========================================================================


class TestRetryPolicy:
    def test_immediate_policy_one_attempt(self):
        assert IMMEDIATE_POLICY.max_attempts == 1
        assert not IMMEDIATE_POLICY.should_retry(1, Exception())

    def test_should_retry_at_max_returns_false(self):
        policy = RetryPolicy(max_attempts=3)
        assert not policy.should_retry(3, Exception())

    def test_should_retry_below_max_returns_true(self):
        policy = RetryPolicy(max_attempts=3)
        assert policy.should_retry(1, Exception())

    def test_retryable_exceptions_filter(self):
        policy = RetryPolicy(max_attempts=3, retryable_exceptions=(ValueError,))
        assert policy.should_retry(1, ValueError("oops"))
        assert not policy.should_retry(1, RuntimeError("nope"))

    def test_linear_backoff(self):
        policy = RetryPolicy(
            max_attempts=3,
            base_delay_seconds=2.0,
            backoff=BackoffStrategy.LINEAR,
            jitter=False,
        )
        assert policy.delay_for_attempt(1) == pytest.approx(2.0)
        assert policy.delay_for_attempt(2) == pytest.approx(4.0)

    def test_exponential_backoff(self):
        policy = RetryPolicy(
            max_attempts=5,
            base_delay_seconds=1.0,
            backoff=BackoffStrategy.EXPONENTIAL,
            jitter=False,
        )
        assert policy.delay_for_attempt(1) == pytest.approx(1.0)
        assert policy.delay_for_attempt(2) == pytest.approx(2.0)
        assert policy.delay_for_attempt(3) == pytest.approx(4.0)

    def test_max_delay_cap(self):
        policy = RetryPolicy(
            max_attempts=10,
            base_delay_seconds=100.0,
            max_delay_seconds=10.0,
            backoff=BackoffStrategy.EXPONENTIAL,
            jitter=False,
        )
        assert policy.delay_for_attempt(5) <= 10.0

    def test_none_backoff(self):
        policy = RetryPolicy(
            max_attempts=3,
            base_delay_seconds=5.0,
            backoff=BackoffStrategy.NONE,
            jitter=False,
        )
        # NONE strategy returns base_delay_seconds unchanged
        assert policy.delay_for_attempt(3) == pytest.approx(5.0)

    def test_predefined_policies_exist(self):
        for p in (
            IMMEDIATE_POLICY,
            FAST_RETRY_POLICY,
            STANDARD_POLICY,
            SLOW_RETRY_POLICY,
        ):
            assert p.max_attempts >= 1


# ===========================================================================
# TestDeadlockDetector
# ===========================================================================


class TestDeadlockDetector:
    def test_track_adds_record(self):
        dd = DeadlockDetector()
        dd.track("jid", "j", "w1", timeout_seconds=60.0)
        assert dd.in_flight_count() == 1

    def test_complete_removes_record(self):
        dd = DeadlockDetector()
        dd.track("jid", "j", "w1", timeout_seconds=60.0)
        assert dd.complete("jid")
        assert dd.in_flight_count() == 0

    def test_complete_missing_returns_false(self):
        dd = DeadlockDetector()
        assert not dd.complete("nope")

    def test_stalled_jobs_empty_when_fresh(self):
        dd = DeadlockDetector()
        dd.track("jid", "j", "w1", timeout_seconds=60.0)
        assert dd.stalled_jobs() == []

    def test_stalled_jobs_detected(self):
        dd = DeadlockDetector()
        dd.track("jid", "j", "w1", timeout_seconds=0.0)
        time.sleep(0.01)
        stalled = dd.stalled_jobs()
        assert any(r.job_id == "jid" for r in stalled)

    def test_elapsed_seconds(self):
        dd = DeadlockDetector()
        dd.track("jid", "j", "w1", timeout_seconds=60.0)
        elapsed = dd.elapsed_seconds("jid")
        assert elapsed is not None and elapsed >= 0.0

    def test_summary_keys(self):
        dd = DeadlockDetector()
        s = dd.summary()
        assert "in_flight" in s


# ===========================================================================
# TestPipelineCoordinator
# ===========================================================================


class TestPipelineCoordinator:
    def _step(self, name, job_name="j", depends_on=None, priority=5):
        return PipelineStep(
            name=name, job_name=job_name, depends_on=depends_on or [], priority=priority
        )

    def test_no_deps(self):
        coord = PipelineCoordinator()
        plan = coord.plan([self._step("a"), self._step("b")])
        assert not plan.has_cycle
        assert len(plan.steps) == 2

    def test_linear_deps(self):
        coord = PipelineCoordinator()
        plan = coord.plan([self._step("b", depends_on=["a"]), self._step("a")])
        names = [s.name for s in plan.steps]
        assert names.index("a") < names.index("b")

    def test_diamond_deps(self):
        coord = PipelineCoordinator()
        steps = [
            self._step("d", depends_on=["b", "c"]),
            self._step("b", depends_on=["a"]),
            self._step("c", depends_on=["a"]),
            self._step("a"),
        ]
        plan = coord.plan(steps)
        assert not plan.has_cycle
        names = [s.name for s in plan.steps]
        assert names.index("a") < names.index("b")
        assert names.index("a") < names.index("c")
        assert names.index("b") < names.index("d")

    def test_cycle_marked(self):
        coord = PipelineCoordinator()
        plan = coord.plan(
            [self._step("a", depends_on=["b"]), self._step("b", depends_on=["a"])]
        )
        assert plan.has_cycle

    def test_unknown_dep_raises(self):
        coord = PipelineCoordinator()
        with pytest.raises(ValueError):
            coord.plan([self._step("a", depends_on=["missing"])])

    def test_ready_steps_empty(self):
        coord = PipelineCoordinator()
        plan = coord.plan([self._step("a", depends_on=["b"]), self._step("b")])
        ready_names = [s.name for s in coord.ready_steps(plan, completed=set())]
        assert ready_names == ["b"]

    def test_ready_steps_after_completion(self):
        coord = PipelineCoordinator()
        plan = coord.plan([self._step("b", depends_on=["a"]), self._step("a")])
        ready_names = [s.name for s in coord.ready_steps(plan, completed={"a"})]
        assert "b" in ready_names

    def test_is_complete_false(self):
        coord = PipelineCoordinator()
        plan = coord.plan([self._step("a")])
        assert not coord.is_complete(plan, completed=set())

    def test_is_complete_true(self):
        coord = PipelineCoordinator()
        plan = coord.plan([self._step("a")])
        assert coord.is_complete(plan, completed={"a"})

    def test_priority_preserved(self):
        coord = PipelineCoordinator()
        plan = coord.plan([self._step("a", priority=9), self._step("b", priority=2)])
        priorities = {s.name: s.priority for s in plan.steps}
        assert priorities["a"] == 9 and priorities["b"] == 2


# ===========================================================================
# TestWorkerMetrics
# ===========================================================================


class TestWorkerMetrics:
    def test_enqueued_counter(self):
        m = WorkerMetrics()
        m.record_enqueued("j")
        assert m.get_stat("j").total_enqueued == 1

    def test_success_counter(self):
        m = WorkerMetrics()
        m.record_success("j", duration_seconds=1.5)
        assert m.get_stat("j").total_succeeded == 1

    def test_failure_counter(self):
        m = WorkerMetrics()
        m.record_failure("j", dead=False)
        assert m.get_stat("j").total_failed == 1

    def test_dead_counter(self):
        m = WorkerMetrics()
        m.record_failure("j", dead=True)
        assert m.get_stat("j").total_dead == 1

    def test_retry_counter(self):
        m = WorkerMetrics()
        m.record_retry("j")
        assert m.get_stat("j").total_retried == 1

    def test_summary_keys(self):
        m = WorkerMetrics()
        m.record_enqueued("j")
        s = m.summary()
        assert s["job_types"] == 1
        assert "total_enqueued" in s

    def test_reset_clears(self):
        m = WorkerMetrics()
        m.record_enqueued("j")
        m.reset()
        assert m.get_stat("j") is None


# ===========================================================================
# TestTaskRouter
# ===========================================================================


class TestTaskRouter:
    def test_register_and_route(self):
        r = TaskRouter()
        r.register("j", _noop)
        assert r.route("j") is _noop

    def test_route_missing_returns_none(self):
        r = TaskRouter()
        assert r.route("missing") is None

    def test_require_route_missing_raises(self):
        r = TaskRouter()
        with pytest.raises(KeyError):
            r.require_route("missing")

    def test_is_routed(self):
        r = TaskRouter()
        r.register("j", _noop)
        assert r.is_routed("j")
        assert not r.is_routed("nope")

    def test_registered_names(self):
        r = TaskRouter()
        r.register("a", _noop)
        r.register("b", _noop)
        assert set(r.registered_names()) == {"a", "b"}

    def test_deregister(self):
        r = TaskRouter()
        r.register("j", _noop)
        r.deregister("j")
        assert not r.is_routed("j")

    def test_overwrite(self):
        r = TaskRouter()
        r.register("j", _noop)
        r.register("j", _boom)
        assert r.route("j") is _boom


# ===========================================================================
# TestWorkersRuntime
# ===========================================================================


class TestWorkersRuntime:
    def _rt(self) -> WorkersRuntime:
        return _runtime_with_handler("test_job")

    def test_submit_unrouted_raises(self):
        rt = WorkersRuntime()
        with pytest.raises(KeyError):
            rt.submit("unknown_job")

    def test_submit_returns_job_id(self):
        rt = self._rt()
        jid = rt.submit("test_job")
        assert isinstance(jid, str)

    def test_execute_one_empty_returns_none(self):
        rt = self._rt()
        assert rt.execute_one() is None

    def test_execute_one_success(self):
        rt = self._rt()
        rt.submit("test_job")
        result = rt.execute_one()
        assert result is not None
        assert result.status == JobStatus.SUCCESS

    def test_execute_one_failure_becomes_dead(self):
        rt = WorkersRuntime(WorkersRuntimeConfig(default_retry_policy=IMMEDIATE_POLICY))
        rt.router.register("fail_job", _boom)
        rt.submit("fail_job")
        result = rt.execute_one()
        assert result.status == JobStatus.DEAD

    def test_retry_then_success(self):
        call_count = {"n": 0}

        def flaky(**kwargs):
            call_count["n"] += 1
            if call_count["n"] < 2:
                raise RuntimeError("transient")
            return "ok"

        policy = RetryPolicy(max_attempts=3, backoff=BackoffStrategy.NONE, jitter=False)
        rt = WorkersRuntime(WorkersRuntimeConfig(default_retry_policy=policy))
        rt.router.register("flaky_job", flaky)
        rt.submit("flaky_job")
        result = rt.execute_one()
        assert result.status == JobStatus.SUCCESS
        assert call_count["n"] == 2

    def test_exhaust_retries_becomes_dead(self):
        policy = RetryPolicy(max_attempts=2, backoff=BackoffStrategy.NONE, jitter=False)
        rt = WorkersRuntime(WorkersRuntimeConfig(default_retry_policy=policy))
        rt.router.register("fail_job", _boom)
        rt.submit("fail_job")
        result = rt.execute_one()
        assert result.status == JobStatus.DEAD

    def test_drain_all(self):
        rt = self._rt()
        for _ in range(5):
            rt.submit("test_job")
        results = rt.drain()
        assert len(results) == 5
        assert rt.queue.is_empty()

    def test_drain_max_jobs(self):
        rt = self._rt()
        for _ in range(5):
            rt.submit("test_job")
        results = rt.drain(max_jobs=3)
        assert len(results) == 3
        assert len(rt.queue) == 2

    def test_health_updated_after_execute(self):
        rt = self._rt()
        rt.submit("test_job")
        rt.execute_one()
        beat = rt.health.get_beat(rt.config.worker_id)
        assert beat is not None

    def test_metrics_updated_after_success(self):
        rt = self._rt()
        rt.submit("test_job")
        rt.execute_one()
        stat = rt.metrics.get_stat("test_job")
        assert stat.total_succeeded == 1

    def test_deadlock_cleared_on_success(self):
        rt = self._rt()
        rt.submit("test_job")
        rt.execute_one()
        assert rt.deadlock.in_flight_count() == 0

    def test_status_summary_keys(self):
        rt = self._rt()
        s = rt.status_summary()
        for key in (
            "queue_depth",
            "health",
            "metrics",
            "deadlock",
            "recent_results",
            "registered_job_types",
            "routed_job_types",
        ):
            assert key in s

    def test_submit_pipeline_ordered(self):
        rt = WorkersRuntime(WorkersRuntimeConfig(default_retry_policy=IMMEDIATE_POLICY))
        rt.router.register("step_job", _noop)
        steps = [
            PipelineStep(name="b", job_name="step_job", depends_on=["a"]),
            PipelineStep(name="a", job_name="step_job"),
        ]
        mapping = rt.submit_pipeline(steps)
        assert set(mapping) == {"a", "b"}
        assert len(rt.queue) == 2

    def test_submit_pipeline_cycle_raises(self):
        rt = WorkersRuntime(WorkersRuntimeConfig(default_retry_policy=IMMEDIATE_POLICY))
        rt.router.register("step_job", _noop)
        steps = [
            PipelineStep(name="a", job_name="step_job", depends_on=["b"]),
            PipelineStep(name="b", job_name="step_job", depends_on=["a"]),
        ]
        with pytest.raises(ValueError):
            rt.submit_pipeline(steps)
