"""Retry queue for failed ingestion runs and records.

Thread-safe, in-memory queue.  Items are scheduled for re-processing at a
configurable future time.  The caller is responsible for processing items
returned by :func:`dequeue_due` and either completing or re-enqueuing them.

Like :mod:`checkpointing`, this structure is transient — it does not persist
across process restarts.  Its purpose is to smooth over transient errors
within a single process lifetime (e.g. a network hiccup that should be
retried 60 seconds later).

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
# key: (source_name, run_id) → RetryItem
_queue: dict[tuple[str, int | None], "RetryItem"] = {}


@dataclass
class RetryItem:
    """A single item pending retry."""

    source_name: str
    run_id: int | None
    reason: str
    attempt: int = 1
    scheduled_at: datetime = field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )
    payload: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def enqueue(
    source_name: str,
    run_id: int | None,
    reason: str,
    *,
    payload: dict[str, Any] | None = None,
    delay_secs: float = 60.0,
) -> RetryItem:
    """Add or update a retry item for *(source_name, run_id)*.

    If an entry already exists for this key the attempt counter is
    incremented and the scheduled time is pushed forward.

    Args:
        source_name: Logical source key.
        run_id:      The ``IngestionRun.id`` to retry (may be ``None``
                     when the run itself failed to open).
        reason:      Short human-readable failure reason.
        payload:     Arbitrary context to pass back to the caller.
        delay_secs:  Seconds from now before the item becomes due.

    Returns:
        The (possibly updated) :class:`RetryItem`.
    """
    key = (source_name, run_id)
    due_at = datetime.now(tz=timezone.utc) + timedelta(seconds=delay_secs)
    with _lock:
        existing = _queue.get(key)
        if existing is not None:
            existing.attempt += 1
            existing.scheduled_at = due_at
            existing.reason = reason
            if payload:
                existing.payload.update(payload)
            item = existing
        else:
            item = RetryItem(
                source_name=source_name,
                run_id=run_id,
                reason=reason,
                attempt=1,
                scheduled_at=due_at,
                payload=deepcopy(payload or {}),
            )
            _queue[key] = item
    _log.debug(
        "retry.enqueue source=%s run_id=%s attempt=%d due=%s",
        source_name,
        run_id,
        item.attempt,
        due_at.isoformat(),
    )
    return deepcopy(item)


def dequeue_due(at: datetime | None = None) -> list[RetryItem]:
    """Remove and return all items whose ``scheduled_at`` is on or before *at*.

    Args:
        at: Reference time (defaults to ``datetime.now(utc)``).

    Returns:
        List of :class:`RetryItem` that are ready for retry; removed from the
        internal queue.  Caller must re-enqueue if the retry fails again.
    """
    ref = at or datetime.now(tz=timezone.utc)
    due: list[RetryItem] = []
    with _lock:
        due_keys = [k for k, v in _queue.items() if v.scheduled_at <= ref]
        for k in due_keys:
            due.append(deepcopy(_queue.pop(k)))
    if due:
        _log.debug("retry.dequeue count=%d", len(due))
    return due


def remove(source_name: str, run_id: int | None) -> bool:
    """Remove a specific item from the queue.

    Returns:
        ``True`` if the item existed and was removed, ``False`` otherwise.
    """
    key = (source_name, run_id)
    with _lock:
        if key in _queue:
            del _queue[key]
            return True
    return False


def list_pending() -> list[dict[str, Any]]:
    """Return a snapshot of all queued items (not yet removed)."""
    with _lock:
        return [
            {
                "source_name": item.source_name,
                "run_id": item.run_id,
                "reason": item.reason,
                "attempt": item.attempt,
                "scheduled_at": item.scheduled_at.isoformat(),
                "payload": deepcopy(item.payload),
            }
            for item in sorted(_queue.values(), key=lambda x: x.scheduled_at)
        ]


def size() -> int:
    """Return the number of items currently in the queue."""
    with _lock:
        return len(_queue)


def clear_all() -> None:
    """Remove all queued items (primarily for test teardown)."""
    with _lock:
        _queue.clear()
