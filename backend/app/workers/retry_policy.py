"""Retry policies with configurable backoff strategies."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Type


class BackoffStrategy(str, Enum):
    NONE = "none"
    LINEAR = "linear"
    EXPONENTIAL = "exponential"
    FIBONACCI = "fibonacci"


@dataclass(frozen=True)
class RetryPolicy:
    """Configures retry count and delay strategy for a failing job."""

    max_attempts: int = 3
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 300.0
    backoff: BackoffStrategy = BackoffStrategy.EXPONENTIAL
    jitter: bool = True
    retryable_exceptions: tuple[Type[Exception], ...] = (Exception,)

    def delay_for_attempt(self, attempt: int, seed: float = 0.5) -> float:
        """Compute delay in seconds before attempt number *attempt* (1-indexed).

        Args:
            attempt: Which try this is (1 = first retry after the initial failure).
            seed:    Deterministic jitter coefficient in ``[0, 1)``.  Use
                     ``random.random()`` in production; a constant for tests.
        """
        if self.backoff == BackoffStrategy.NONE:
            base = self.base_delay_seconds
        elif self.backoff == BackoffStrategy.LINEAR:
            base = self.base_delay_seconds * attempt
        elif self.backoff == BackoffStrategy.EXPONENTIAL:
            base = self.base_delay_seconds * (2 ** (attempt - 1))
        elif self.backoff == BackoffStrategy.FIBONACCI:
            base = self.base_delay_seconds * _fib(attempt)
        else:
            base = self.base_delay_seconds

        delay = min(base, self.max_delay_seconds)
        if self.jitter:
            delay = delay * (1.0 + 0.5 * seed)
        return delay

    def should_retry(self, attempt: int, exc: Exception | None = None) -> bool:
        """Return ``True`` when the job should be retried after *attempt*.

        Retries are refused once ``attempt >= max_attempts`` or when *exc*
        is not an instance of any type in ``retryable_exceptions``.
        """
        if attempt >= self.max_attempts:
            return False
        if exc is None:
            return True
        return isinstance(exc, self.retryable_exceptions)


# ---------------------------------------------------------------------------
# Fibonacci helper
# ---------------------------------------------------------------------------


def _fib(n: int) -> int:
    """Return the *n*-th Fibonacci number (1-indexed, starting at 1, 1, 2, ...)."""
    a, b = 1, 1
    for _ in range(n - 1):
        a, b = b, a + b
    return a


# ---------------------------------------------------------------------------
# Predefined policies
# ---------------------------------------------------------------------------

IMMEDIATE_POLICY = RetryPolicy(
    max_attempts=1,
    backoff=BackoffStrategy.NONE,
    jitter=False,
)

FAST_RETRY_POLICY = RetryPolicy(
    max_attempts=3,
    base_delay_seconds=0.1,
    backoff=BackoffStrategy.LINEAR,
    jitter=False,
)

STANDARD_POLICY = RetryPolicy(
    max_attempts=3,
    base_delay_seconds=1.0,
    backoff=BackoffStrategy.EXPONENTIAL,
)

SLOW_RETRY_POLICY = RetryPolicy(
    max_attempts=5,
    base_delay_seconds=5.0,
    backoff=BackoffStrategy.EXPONENTIAL,
)
