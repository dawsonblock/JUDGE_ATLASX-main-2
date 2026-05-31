"""Circuit breaker — tick-based open / half-open / closed state machine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional


class BreakerState(str, Enum):
    CLOSED = "closed"  # normal operation
    OPEN = "open"  # failing — reject calls immediately
    HALF_OPEN = "half_open"  # probing — one trial call allowed


@dataclass
class CircuitBreaker:
    """
    Failure-count circuit breaker with tick-based cooldown.

    Usage::
        cb = CircuitBreaker(failure_threshold=3, recovery_ticks=5)
        if cb.allow():
            try:
                do_work()
                cb.record_success()
            except Exception:
                cb.record_failure()
    """

    failure_threshold: int = 3  # failures before opening
    recovery_ticks: int = 10  # ticks in OPEN before moving to HALF_OPEN
    half_open_successes: int = 1  # consecutive successes needed to close

    _state: BreakerState = field(default=BreakerState.CLOSED, init=False)
    _failure_count: int = field(default=0, init=False)
    _success_streak: int = field(default=0, init=False)
    _ticks_open: int = field(default=0, init=False)
    _history: List[str] = field(default_factory=list, init=False)  # "ok"|"fail"

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    def allow(self) -> bool:
        """Return True if a call should be allowed through."""
        if self._state == BreakerState.CLOSED:
            return True
        if self._state == BreakerState.HALF_OPEN:
            return True
        # OPEN — block unless cooldown elapsed
        return False

    def record_success(self) -> None:
        self._history.append("ok")
        if self._state == BreakerState.HALF_OPEN:
            self._success_streak += 1
            if self._success_streak >= self.half_open_successes:
                self._close()
        elif self._state == BreakerState.CLOSED:
            self._failure_count = 0

    def record_failure(self) -> None:
        self._history.append("fail")
        if self._state == BreakerState.HALF_OPEN:
            # One failure sends back to OPEN
            self._open()
            return
        if self._state == BreakerState.CLOSED:
            self._failure_count += 1
            if self._failure_count >= self.failure_threshold:
                self._open()

    def tick(self) -> None:
        """Advance one time unit (call periodically, e.g. per second)."""
        if self._state == BreakerState.OPEN:
            self._ticks_open += 1
            if self._ticks_open >= self.recovery_ticks:
                self._half_open()

    # ------------------------------------------------------------------
    # State transitions
    # ------------------------------------------------------------------

    def _open(self) -> None:
        self._state = BreakerState.OPEN
        self._ticks_open = 0
        self._success_streak = 0

    def _half_open(self) -> None:
        self._state = BreakerState.HALF_OPEN
        self._success_streak = 0

    def _close(self) -> None:
        self._state = BreakerState.CLOSED
        self._failure_count = 0
        self._success_streak = 0
        self._ticks_open = 0

    # ------------------------------------------------------------------
    # Inspection
    # ------------------------------------------------------------------

    @property
    def state(self) -> BreakerState:
        return self._state

    @property
    def failure_count(self) -> int:
        return self._failure_count

    @property
    def is_open(self) -> bool:
        return self._state == BreakerState.OPEN

    @property
    def is_closed(self) -> bool:
        return self._state == BreakerState.CLOSED

    @property
    def is_half_open(self) -> bool:
        return self._state == BreakerState.HALF_OPEN

    def reset(self) -> None:
        self._close()
        self._history.clear()

    def history(self) -> List[str]:
        return list(self._history)

    def error_rate(self) -> float:
        """Fraction of recent history entries that are failures."""
        if not self._history:
            return 0.0
        return self._history.count("fail") / len(self._history)


__all__ = ["BreakerState", "CircuitBreaker"]
