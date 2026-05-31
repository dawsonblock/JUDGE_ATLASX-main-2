"""Workers runtime — synchronous job executor wiring all subsystems together."""

from __future__ import annotations

import logging
import time
import traceback
from dataclasses import dataclass, field
from typing import Any

from app.workers.deadlock_detector import DeadlockDetector
from app.workers.job_queue import JobEnvelope, JobQueue, Priority
from app.workers.job_registry import JobRegistry
from app.workers.job_result import JobResult, JobStatus, ResultStore
from app.workers.pipeline_coordinator import PipelineCoordinator, PipelineStep
from app.workers.retry_policy import RetryPolicy, STANDARD_POLICY
from app.workers.task_router import TaskRouter
from app.workers.worker_health import WorkerHealthMonitor, WorkerState
from app.workers.worker_metrics import WorkerMetrics

log = logging.getLogger(__name__)


@dataclass
class WorkersRuntimeConfig:
    """Configuration knobs for :class:`WorkersRuntime`."""

    worker_id: str = "workers-runtime-0"
    heartbeat_stale_seconds: float = 60.0
    result_store_max_size: int = 1000
    default_retry_policy: RetryPolicy = field(default_factory=lambda: STANDARD_POLICY)


class WorkersRuntime:
    """Synchronous, single-threaded workers runtime.

    Designed for deterministic testing; all concurrency is deferred to the
    caller (e.g. APScheduler, FastAPI BackgroundTasks, or a thread pool).

    Features
    --------
    - Priority job queue
    - Job type registry and task routing
    - Inline retry with configurable back-off policy
    - In-flight deadlock detection
    - Worker health heartbeats
    - Execution metrics
    - Multi-step pipeline coordination (dependency ordering)
    """

    def __init__(self, config: WorkersRuntimeConfig | None = None) -> None:
        self.config = config or WorkersRuntimeConfig()
        self.queue = JobQueue()
        self.registry = JobRegistry()
        self.router = TaskRouter()
        self.results = ResultStore(max_size=self.config.result_store_max_size)
        self.health = WorkerHealthMonitor(
            stale_seconds=self.config.heartbeat_stale_seconds
        )
        self.metrics = WorkerMetrics()
        self.deadlock = DeadlockDetector()
        self.coordinator = PipelineCoordinator()

    # ------------------------------------------------------------------
    # Job submission
    # ------------------------------------------------------------------

    def submit(
        self,
        job_name: str,
        payload: dict[str, Any] | None = None,
        *,
        priority: int = Priority.NORMAL,
        job_id: str | None = None,
    ) -> str:
        """Enqueue *job_name* and return its job_id.

        Raises ``KeyError`` if no handler has been registered for the job.
        """
        if not self.router.is_routed(job_name):
            raise KeyError(f"No handler registered for job: {job_name!r}")
        if payload is None:
            payload = {}
        job_id = self.queue.enqueue(
            job_name=job_name,
            payload=payload,
            priority=priority,
            job_id=job_id,
        )
        self.metrics.record_enqueued(job_name)
        log.debug("Submitted job %s (id=%s, priority=%s)", job_name, job_id, priority)
        return job_id

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    def execute_one(
        self, *, retry_policy: RetryPolicy | None = None
    ) -> JobResult | None:
        """Dequeue and execute the highest-priority job.

        Retries inline up to ``retry_policy.max_attempts`` times.
        Returns ``None`` when the queue is empty.
        """
        env = self.queue.dequeue()
        if env is None:
            return None

        policy = retry_policy or self.config.default_retry_policy
        handler = self.router.route(env.job_name)

        if handler is None:
            result = JobResult(
                job_id=env.job_id,
                job_name=env.job_name,
                status=JobStatus.DEAD,
                attempt=1,
                started_at=time.monotonic(),
                finished_at=time.monotonic(),
                error="No handler registered for job type",
            )
            self.results.record(result)
            self.metrics.record_failure(env.job_name, dead=True)
            return result

        spec = self.registry.get(env.job_name)
        timeout = spec.timeout_seconds if spec else 300.0

        for attempt in range(1, policy.max_attempts + 1):
            self.health.heartbeat(
                self.config.worker_id,
                WorkerState.BUSY,
                current_job_id=env.job_id,
                current_job_name=env.job_name,
            )
            self.deadlock.track(
                job_id=env.job_id,
                job_name=env.job_name,
                worker_id=self.config.worker_id,
                timeout_seconds=timeout,
                attempt=attempt,
            )

            started_at = time.monotonic()
            try:
                output = handler(**env.payload)
                finished_at = time.monotonic()
                self.deadlock.complete(env.job_id)

                result = JobResult(
                    job_id=env.job_id,
                    job_name=env.job_name,
                    status=JobStatus.SUCCESS,
                    attempt=attempt,
                    started_at=started_at,
                    finished_at=finished_at,
                    output=output,
                )
                self.results.record(result)
                self.metrics.record_success(env.job_name, result.duration_seconds)
                self.health.heartbeat(self.config.worker_id, WorkerState.IDLE)
                log.debug(
                    "Job succeeded: %s (id=%s, attempt=%s, %.3fs)",
                    env.job_name,
                    env.job_id,
                    attempt,
                    result.duration_seconds,
                )
                return result

            except Exception as exc:
                finished_at = time.monotonic()
                self.deadlock.complete(env.job_id)
                error_msg = str(exc)
                tb_str = traceback.format_exc()
                is_last = (attempt == policy.max_attempts) or not policy.should_retry(
                    attempt, exc
                )

                if not is_last:
                    # Record intermediate RETRY result and try again.
                    retry_result = JobResult(
                        job_id=env.job_id,
                        job_name=env.job_name,
                        status=JobStatus.RETRY,
                        attempt=attempt,
                        started_at=started_at,
                        finished_at=finished_at,
                        error=error_msg,
                        traceback=tb_str,
                    )
                    self.results.record(retry_result)
                    self.metrics.record_retry(env.job_name)
                    log.warning(
                        "Job %s will retry (attempt %s/%s): %s",
                        env.job_name,
                        attempt,
                        policy.max_attempts,
                        error_msg,
                    )
                    continue

                # Exhausted — mark DEAD.
                dead_result = JobResult(
                    job_id=env.job_id,
                    job_name=env.job_name,
                    status=JobStatus.DEAD,
                    attempt=attempt,
                    started_at=started_at,
                    finished_at=finished_at,
                    error=error_msg,
                    traceback=tb_str,
                )
                self.results.record(dead_result)
                self.metrics.record_failure(env.job_name, dead=True)
                self.health.heartbeat(self.config.worker_id, WorkerState.IDLE)
                log.error(
                    "Job dead: %s (id=%s, attempt=%s): %s",
                    env.job_name,
                    env.job_id,
                    attempt,
                    error_msg,
                )
                return dead_result

        return None  # unreachable but satisfies type checker

    def drain(
        self,
        max_jobs: int | None = None,
        *,
        retry_policy: RetryPolicy | None = None,
    ) -> list[JobResult]:
        """Execute all queued jobs (or up to *max_jobs*).

        Returns the list of :class:`JobResult` objects in execution order.
        """
        results: list[JobResult] = []
        count = 0
        while not self.queue.is_empty():
            if max_jobs is not None and count >= max_jobs:
                break
            result = self.execute_one(retry_policy=retry_policy)
            if result is not None:
                results.append(result)
                count += 1
        self.health.heartbeat(self.config.worker_id, WorkerState.IDLE)
        return results

    # ------------------------------------------------------------------
    # Pipeline submission
    # ------------------------------------------------------------------

    def submit_pipeline(
        self,
        steps: list[PipelineStep],
        *,
        base_priority: int = Priority.NORMAL,
    ) -> dict[str, str]:
        """Submit a multi-step pipeline in dependency order.

        Returns a mapping of ``step_name → job_id``.
        Raises ``ValueError`` if *steps* contain a dependency cycle.
        """
        plan = self.coordinator.plan(steps)
        if plan.has_cycle:
            raise ValueError("Pipeline contains a dependency cycle; cannot submit")

        step_to_job_id: dict[str, str] = {}
        for step in plan.steps:
            effective_priority = max(1, min(10, step.priority + base_priority - 5))
            job_id = self.submit(
                job_name=step.job_name,
                payload=step.payload,
                priority=effective_priority,
            )
            step_to_job_id[step.name] = job_id
        return step_to_job_id

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    def status_summary(self) -> dict[str, Any]:
        """Return a unified status snapshot of the runtime."""
        return {
            "queue_depth": len(self.queue),
            "health": self.health.summary(),
            "metrics": self.metrics.summary(),
            "deadlock": self.deadlock.summary(),
            "recent_results": len(self.results),
            "registered_job_types": self.registry.list_names(),
            "routed_job_types": self.router.registered_names(),
        }
