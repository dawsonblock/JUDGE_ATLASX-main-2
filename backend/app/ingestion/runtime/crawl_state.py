"""Crawl state manager.

Tracks per-source pagination/offset progress for long-running crawls that
span many pages or API offsets.  This is a finer-grained companion to
:mod:`checkpointing` — where checkpoints record the *resume* cursor, crawl
state records the *in-flight* progress of an active crawl.

In-memory only (no DB table) — survives intra-process pagination but is
reset on process restart.

Thread-safety: A ``threading.Lock`` guards all state mutations.
"""

from __future__ import annotations

import logging
import threading
from copy import deepcopy
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

_log = logging.getLogger(__name__)
_lock = threading.Lock()
_states: dict[str, "_InternalState"] = {}


@dataclass
class _InternalState:
    source_name: str
    cursor: Any
    total_fetched: int
    page: int
    started_at: datetime
    updated_at: datetime


@dataclass
class CrawlState:
    """Immutable snapshot of a source's crawl progress."""

    source_name: str
    cursor: Any
    total_fetched: int
    page: int
    started_at: datetime
    updated_at: datetime


def _snapshot(s: _InternalState) -> CrawlState:
    return CrawlState(
        source_name=s.source_name,
        cursor=deepcopy(s.cursor),
        total_fetched=s.total_fetched,
        page=s.page,
        started_at=s.started_at,
        updated_at=s.updated_at,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def start(source_name: str, *, initial_cursor: Any = None) -> CrawlState:
    """Begin tracking a new crawl for *source_name*.

    Overwrites any existing in-flight state for this source.

    Args:
        source_name:    Logical source key.
        initial_cursor: Optional starting cursor (e.g. ``{"offset": 0}``).

    Returns:
        The initial :class:`CrawlState`.
    """
    now = datetime.now(tz=timezone.utc)
    state = _InternalState(
        source_name=source_name,
        cursor=deepcopy(initial_cursor),
        total_fetched=0,
        page=0,
        started_at=now,
        updated_at=now,
    )
    with _lock:
        _states[source_name] = state
    _log.debug("crawl.start source=%s cursor=%r", source_name, initial_cursor)
    return _snapshot(state)


def advance(
    source_name: str,
    cursor: Any,
    fetched_count: int,
) -> CrawlState:
    """Advance the crawl cursor after fetching a batch of records.

    Args:
        source_name:  Logical source key.
        cursor:       Updated cursor describing where to resume.
        fetched_count: Number of records fetched in this batch.

    Returns:
        The updated :class:`CrawlState`.

    Raises:
        KeyError: If *source_name* was not started via :func:`start`.
    """
    with _lock:
        state = _states.get(source_name)
        if state is None:
            raise KeyError(f"No active crawl for source_name={source_name!r}")
        state.cursor = deepcopy(cursor)
        state.total_fetched += fetched_count
        state.page += 1
        state.updated_at = datetime.now(tz=timezone.utc)
        snap = _snapshot(state)
    _log.debug(
        "crawl.advance source=%s page=%d total_fetched=%d cursor=%r",
        source_name,
        snap.page,
        snap.total_fetched,
        cursor,
    )
    return snap


def get(source_name: str) -> CrawlState | None:
    """Return the current crawl state for *source_name*, or ``None``."""
    with _lock:
        state = _states.get(source_name)
        return _snapshot(state) if state is not None else None


def finish(source_name: str) -> None:
    """Remove the crawl state for *source_name* (crawl complete or abandoned)."""
    with _lock:
        _states.pop(source_name, None)
    _log.debug("crawl.finish source=%s", source_name)


def list_active() -> list[dict[str, Any]]:
    """Return a list of all in-flight crawl states."""
    with _lock:
        return [
            {
                "source_name": s.source_name,
                "cursor": deepcopy(s.cursor),
                "total_fetched": s.total_fetched,
                "page": s.page,
                "started_at": s.started_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
            }
            for s in _states.values()
        ]


def clear_all() -> None:
    """Remove all crawl states (primarily for test teardown)."""
    with _lock:
        _states.clear()
