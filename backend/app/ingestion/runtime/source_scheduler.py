"""Source scheduler.

Maintains an in-memory schedule of when each named source should next be
polled.  Intervals are expressed in seconds.

This is an in-memory structure only — it survives within a single process
lifetime but is rebuilt from configuration on restart.  Callers are
expected to persist schedule configuration externally (e.g. via
``SourceRegistry`` table) and re-register after process start.

Thread-safety: A ``threading.Lock`` guards all state mutations.
"""

from __future__ import annotations

import logging
import threading
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

_log = logging.getLogger(__name__)
_lock = threading.Lock()
_schedule: dict[str, "_ScheduleEntry"] = {}


@dataclass
class _ScheduleEntry:
    source_name: str
    interval_seconds: int
    enabled: bool = True
    last_run: datetime | None = None
    next_run: datetime | None = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def register(
    source_name: str,
    interval_seconds: int,
    *,
    enabled: bool = True,
) -> None:
    """Register (or re-register) a source with a polling interval.

    If a previous registration exists its ``last_run`` / ``next_run`` are
    preserved unless ``interval_seconds`` changes, in which case ``next_run``
    is recalculated.

    Args:
        source_name:       Logical key matching ``SourceRegistry.source_key``.
        interval_seconds:  How often to poll this source (in wall-clock seconds).
        enabled:           Whether the source participates in scheduling.
    """
    now = datetime.now(tz=timezone.utc)
    with _lock:
        existing = _schedule.get(source_name)
        if existing is not None:
            existing.enabled = enabled
            if existing.interval_seconds != interval_seconds:
                existing.interval_seconds = interval_seconds
                # Recalculate next_run based on last_run or now
                base = existing.last_run or now
                existing.next_run = base + timedelta(seconds=interval_seconds)
        else:
            entry = _ScheduleEntry(
                source_name=source_name,
                interval_seconds=interval_seconds,
                enabled=enabled,
                next_run=now,  # eligible immediately on first registration
            )
            _schedule[source_name] = entry
    _log.debug(
        "scheduler.register source=%s interval=%ds", source_name, interval_seconds
    )


def due_sources(at: datetime | None = None) -> list[str]:
    """Return names of sources whose ``next_run`` is on or before *at*.

    Args:
        at: Reference time (defaults to ``datetime.now(utc)``).

    Returns:
        Sorted list of source names due for a run.
    """
    ref = at or datetime.now(tz=timezone.utc)
    with _lock:
        return sorted(
            name
            for name, entry in _schedule.items()
            if entry.enabled and entry.next_run is not None and entry.next_run <= ref
        )


def mark_ran(source_name: str, *, at: datetime | None = None) -> None:
    """Record that *source_name* just ran and advance its ``next_run``.

    Args:
        source_name: Source that completed a run.
        at:          Completion timestamp (defaults to ``datetime.now(utc)``).
    """
    ran_at = at or datetime.now(tz=timezone.utc)
    with _lock:
        entry = _schedule.get(source_name)
        if entry is None:
            _log.warning("scheduler.mark_ran unknown source=%s", source_name)
            return
        entry.last_run = ran_at
        entry.next_run = ran_at + timedelta(seconds=entry.interval_seconds)
    _log.debug("scheduler.mark_ran source=%s next_run=%s", source_name, entry.next_run)


def enable(source_name: str) -> None:
    """Enable scheduling for *source_name*."""
    with _lock:
        if source_name in _schedule:
            _schedule[source_name].enabled = True


def disable(source_name: str) -> None:
    """Disable scheduling for *source_name* (it will not appear in :func:`due_sources`)."""
    with _lock:
        if source_name in _schedule:
            _schedule[source_name].enabled = False


def list_schedule() -> list[dict[str, Any]]:
    """Return a snapshot of all registered schedule entries."""
    with _lock:
        return [
            {
                "source_name": e.source_name,
                "interval_seconds": e.interval_seconds,
                "enabled": e.enabled,
                "last_run": e.last_run.isoformat() if e.last_run else None,
                "next_run": e.next_run.isoformat() if e.next_run else None,
            }
            for e in _schedule.values()
        ]


def clear_all() -> None:
    """Remove all schedule entries (primarily for test teardown)."""
    with _lock:
        _schedule.clear()
