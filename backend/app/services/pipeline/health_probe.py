"""Health probe — rolling window of probe results with a scored status."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class ProbeStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


@dataclass(frozen=True)
class ProbeRecord:
    """Single health observation."""

    status: ProbeStatus
    tick: int
    detail: str = ""


@dataclass
class HealthProbe:
    """
    Records probe results in a sliding window and derives a health score.

    health_score:
        1.0  → score > 0.8  → HEALTHY
        0.4–0.8             → DEGRADED
        < 0.4               → UNHEALTHY
    """

    name: str = "default"
    window_size: int = 20

    _records: List[ProbeRecord] = field(default_factory=list, init=False)

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        status: ProbeStatus,
        tick: int = 0,
        detail: str = "",
    ) -> None:
        self._records.append(ProbeRecord(status=status, tick=tick, detail=detail))
        if len(self._records) > self.window_size:
            del self._records[: len(self._records) - self.window_size]

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def health_score(self) -> float:
        """Fraction of HEALTHY entries in the current window (0.0–1.0)."""
        if not self._records:
            return 1.0  # no data → optimistic
        healthy_count = sum(1 for r in self._records if r.status == ProbeStatus.HEALTHY)
        return healthy_count / len(self._records)

    def current_status(self) -> ProbeStatus:
        score = self.health_score()
        if score > 0.8:
            return ProbeStatus.HEALTHY
        if score > 0.4:
            return ProbeStatus.DEGRADED
        return ProbeStatus.UNHEALTHY

    def is_healthy(self) -> bool:
        return self.current_status() == ProbeStatus.HEALTHY

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    def history(self) -> List[ProbeRecord]:
        return list(self._records)

    def window_count(self) -> int:
        """Actual number of records currently stored."""
        return len(self._records)

    def latest(self) -> Optional[ProbeRecord]:
        return self._records[-1] if self._records else None

    def clear(self) -> None:
        self._records.clear()


__all__ = ["ProbeStatus", "ProbeRecord", "HealthProbe"]
