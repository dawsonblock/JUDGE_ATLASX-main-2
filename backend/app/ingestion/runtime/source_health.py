"""Source health tracker.

Tracks per-source health metrics derived from ``IngestionRun`` outcomes.
Metrics are kept in memory; the underlying ``IngestionRun`` table is used
only for historical replay of past outcomes (via :meth:`SourceHealth.refresh`).

No new database tables are created — all state is computed from the
existing ``IngestionRun`` rows.

Thread-safety: A ``threading.Lock`` guards all in-memory mutations.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import IngestionRun

_log = logging.getLogger(__name__)
_lock = threading.Lock()
_metrics: dict[str, "_HealthMetrics"] = {}


@dataclass
class _HealthMetrics:
    source_name: str
    last_success: datetime | None = None
    last_failure: datetime | None = None
    consecutive_failures: int = 0
    total_runs: int = 0
    success_count: int = 0
    failure_count: int = 0


@dataclass
class HealthSnapshot:
    """Read-only view of a source's current health."""

    source_name: str
    last_success: datetime | None
    last_failure: datetime | None
    consecutive_failures: int
    total_runs: int
    success_rate: float  # 0.0 – 1.0
    is_healthy: bool


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_or_create(source_name: str) -> _HealthMetrics:
    """Return (creating if necessary) the in-memory metrics for *source_name*."""
    if source_name not in _metrics:
        _metrics[source_name] = _HealthMetrics(source_name=source_name)
    return _metrics[source_name]


def _snapshot(m: _HealthMetrics, max_consecutive_failures: int = 3) -> HealthSnapshot:
    rate = m.success_count / m.total_runs if m.total_runs else 0.0
    healthy = m.consecutive_failures < max_consecutive_failures
    return HealthSnapshot(
        source_name=m.source_name,
        last_success=m.last_success,
        last_failure=m.last_failure,
        consecutive_failures=m.consecutive_failures,
        total_runs=m.total_runs,
        success_rate=rate,
        is_healthy=healthy,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def record_success(source_name: str, run_id: int | None = None) -> None:
    """Record that a run for *source_name* succeeded.

    Args:
        source_name: Logical source key.
        run_id:      Associated ``IngestionRun.id`` (informational).
    """
    now = datetime.now(tz=timezone.utc)
    with _lock:
        m = _get_or_create(source_name)
        m.last_success = now
        m.consecutive_failures = 0
        m.total_runs += 1
        m.success_count += 1
    _log.debug("health.success source=%s run_id=%s", source_name, run_id)


def record_failure(
    source_name: str,
    run_id: int | None = None,
    error: str | None = None,
) -> None:
    """Record that a run for *source_name* failed.

    Args:
        source_name: Logical source key.
        run_id:      Associated ``IngestionRun.id`` (informational).
        error:       Short error description (logged only).
    """
    now = datetime.now(tz=timezone.utc)
    with _lock:
        m = _get_or_create(source_name)
        m.last_failure = now
        m.consecutive_failures += 1
        m.total_runs += 1
        m.failure_count += 1
    _log.warning(
        "health.failure source=%s run_id=%s error=%s consecutive=%d",
        source_name,
        run_id,
        error,
        _metrics[source_name].consecutive_failures,
    )


def get_snapshot(
    source_name: str,
    *,
    max_consecutive_failures: int = 3,
) -> HealthSnapshot:
    """Return a :class:`HealthSnapshot` for *source_name*.

    Initialises a zero-value snapshot if the source has never been recorded.
    """
    with _lock:
        m = _get_or_create(source_name)
        return _snapshot(m, max_consecutive_failures)


def get_all_snapshots(
    *,
    max_consecutive_failures: int = 3,
) -> list[HealthSnapshot]:
    """Return snapshots for all tracked sources, sorted by name."""
    with _lock:
        return sorted(
            (_snapshot(m, max_consecutive_failures) for m in _metrics.values()),
            key=lambda s: s.source_name,
        )


def is_healthy(source_name: str, *, max_consecutive_failures: int = 3) -> bool:
    """Convenience predicate — returns ``True`` if the source is considered healthy."""
    return get_snapshot(
        source_name, max_consecutive_failures=max_consecutive_failures
    ).is_healthy


def refresh_from_db(db: Session, source_name: str, *, limit: int = 50) -> None:
    """Rebuild in-memory metrics for *source_name* from recent ``IngestionRun`` rows.

    This is useful after a process restart to restore health state from
    persisted data.  Only the most recent *limit* runs are considered.

    Args:
        db:          Open SQLAlchemy session.
        source_name: Source to refresh.
        limit:       How many recent runs to scan (default 50).
    """
    rows: list[IngestionRun] = (
        db.query(IngestionRun)
        .filter(IngestionRun.source_name == source_name)
        .order_by(IngestionRun.started_at.desc())
        .limit(limit)
        .all()
    )
    with _lock:
        m = _get_or_create(source_name)
        # Reset and replay
        m.consecutive_failures = 0
        m.total_runs = 0
        m.success_count = 0
        m.failure_count = 0
        m.last_success = None
        m.last_failure = None
        # Process oldest-first so consecutive_failures reflects latest streak
        for row in reversed(rows):
            m.total_runs += 1
            if row.status in ("complete", "partial"):
                m.consecutive_failures = 0
                m.success_count += 1
                ts = row.finished_at or row.started_at
                if ts and (m.last_success is None or ts > m.last_success):
                    m.last_success = ts
            else:
                m.consecutive_failures += 1
                m.failure_count += 1
                ts = row.finished_at or row.started_at
                if ts and (m.last_failure is None or ts > m.last_failure):
                    m.last_failure = ts


def clear_all() -> None:
    """Remove all tracked health data (primarily for test teardown)."""
    with _lock:
        _metrics.clear()
