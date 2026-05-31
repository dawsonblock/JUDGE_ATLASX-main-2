"""Pipeline runtime — orchestrator that wires StageRegistry, ServiceLocator,
PipelineMetrics, and CircuitBreaker together."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.services.pipeline.circuit_breaker import BreakerState, CircuitBreaker
from app.services.pipeline.pipeline_metrics import PipelineMetrics
from app.services.pipeline.service_locator import ServiceLocator
from app.services.pipeline.stage_registry import StageRegistry


@dataclass
class PipelineRuntime:
    """
    Execute pipeline stages with optional circuit-breaking and metrics.

    Example::
        reg = StageRegistry()
        reg.register("norm", lambda p: {**p, "normalised": True})
        rt = PipelineRuntime(registry=reg)
        result = rt.run("norm", {"raw": True})
    """

    registry: StageRegistry = field(default_factory=StageRegistry)
    locator: ServiceLocator = field(default_factory=ServiceLocator)
    metrics: PipelineMetrics = field(default_factory=PipelineMetrics)
    _breakers: Dict[str, CircuitBreaker] = field(default_factory=dict, init=False)

    # ------------------------------------------------------------------
    # Circuit-breaker management
    # ------------------------------------------------------------------

    def add_circuit_breaker(self, stage_name: str, breaker: CircuitBreaker) -> None:
        self._breakers[stage_name] = breaker

    def get_circuit_breaker(self, stage_name: str) -> Optional[CircuitBreaker]:
        return self._breakers.get(stage_name)

    # ------------------------------------------------------------------
    # Execution helpers
    # ------------------------------------------------------------------

    def _check_circuit(self, stage_name: str) -> None:
        breaker = self._breakers.get(stage_name)
        if breaker is not None and not breaker.allow():
            raise RuntimeError(
                f"Circuit breaker OPEN for stage '{stage_name}'; call rejected."
            )

    def _report_to_circuit(self, stage_name: str, success: bool) -> None:
        breaker = self._breakers.get(stage_name)
        if breaker is None:
            return
        if success:
            breaker.record_success()
        else:
            breaker.record_failure()

    # ------------------------------------------------------------------
    # Single-stage execution
    # ------------------------------------------------------------------

    def run(self, stage_name: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a single named stage.

        Raises
        ------
        KeyError
            If *stage_name* is not registered.
        RuntimeError
            If the circuit breaker for this stage is OPEN.
        """
        fn = self.registry.get_fn(stage_name)
        if fn is None:
            raise KeyError(f"Stage '{stage_name}' not found in registry.")

        self._check_circuit(stage_name)

        t_start = time.monotonic()
        success = True
        try:
            result = fn(payload)
            return result
        except Exception:
            success = False
            raise
        finally:
            duration_ms = (time.monotonic() - t_start) * 1000.0
            self.metrics.record_execution(stage_name, duration_ms, success)
            self._report_to_circuit(stage_name, success)

    # ------------------------------------------------------------------
    # Chained execution
    # ------------------------------------------------------------------

    def run_sequence(
        self,
        stage_names: List[str],
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute stages in order, passing each stage's output as the next
        stage's input.
        """
        current = dict(payload)
        for name in stage_names:
            current = self.run(name, current)
        return current

    # ------------------------------------------------------------------
    # Tag-based execution
    # ------------------------------------------------------------------

    def run_tagged(
        self,
        tag: str,
        payload: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        """
        Run all *enabled* stages that carry *tag*, each with an independent
        copy of *payload*.  Results are collected in priority order.
        """
        results: List[Dict[str, Any]] = []
        for descriptor in self.registry.stages_with_tag(tag):
            if not descriptor.is_enabled():
                continue
            results.append(self.run(descriptor.name, dict(payload)))
        return results

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> Dict[str, Any]:
        enabled_stages = self.registry.enabled_stages()
        breaker_states: Dict[str, str] = {
            name: b.state.value for name, b in self._breakers.items()
        }
        return {
            "enabled_stage_count": len(enabled_stages),
            "stage_names": [s.name for s in enabled_stages],
            "metrics": self.metrics.snapshot(),
            "circuit_breakers": breaker_states,
        }


__all__ = ["PipelineRuntime"]
