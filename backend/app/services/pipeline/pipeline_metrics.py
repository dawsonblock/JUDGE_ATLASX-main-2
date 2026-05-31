"""Pipeline metrics — per-stage execution counters and duration tracking."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class _StageStats:
    executions: int = 0
    failures: int = 0
    total_duration_ms: float = 0.0

    @property
    def successes(self) -> int:
        return self.executions - self.failures

    def success_rate(self) -> float:
        if self.executions == 0:
            return 0.0
        return self.successes / self.executions

    def average_duration(self) -> Optional[float]:
        if self.executions == 0:
            return None
        return self.total_duration_ms / self.executions

    def as_dict(self) -> Dict[str, Any]:
        return {
            "executions": self.executions,
            "failures": self.failures,
            "successes": self.successes,
            "success_rate": self.success_rate(),
            "average_duration_ms": self.average_duration(),
        }


@dataclass
class PipelineMetrics:
    """Lightweight counters for stage-level monitoring. No I/O, no threads."""

    _stats: Dict[str, _StageStats] = field(default_factory=dict, init=False)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record_execution(
        self,
        stage_name: str,
        duration_ms: float = 0.0,
        success: bool = True,
    ) -> None:
        if stage_name not in self._stats:
            self._stats[stage_name] = _StageStats()
        s = self._stats[stage_name]
        s.executions += 1
        s.total_duration_ms += duration_ms
        if not success:
            s.failures += 1

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def execution_count(self, stage_name: str) -> int:
        return self._stats[stage_name].executions if stage_name in self._stats else 0

    def failure_count(self, stage_name: str) -> int:
        return self._stats[stage_name].failures if stage_name in self._stats else 0

    def success_rate(self, stage_name: str) -> float:
        if stage_name not in self._stats:
            return 0.0
        return self._stats[stage_name].success_rate()

    def average_duration(self, stage_name: str) -> Optional[float]:
        if stage_name not in self._stats:
            return None
        return self._stats[stage_name].average_duration()

    def all_stage_names(self) -> List[str]:
        return sorted(self._stats.keys())

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self, stage_name: str) -> None:
        self._stats.pop(stage_name, None)

    def reset_all(self) -> None:
        self._stats.clear()

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> Dict[str, Any]:
        return {name: stats.as_dict() for name, stats in sorted(self._stats.items())}


__all__ = ["PipelineMetrics"]
