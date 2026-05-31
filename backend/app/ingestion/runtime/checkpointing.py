"""Ingestion checkpoint / resume support.

Checkpoints are stored purely in memory (keyed by source_name) and are
*not* persisted to the database.  They survive intra-process retries but
are cleared on process restart – which is intentional: a cold-start
always re-fetches from the last known-good cursor stored in IngestionRun
metadata.

Typical cursor shapes (all JSON-serialisable):
  {"offset": 1500}
  {"page": 3, "since": "2024-01-01T00:00:00Z"}
  {"last_id": "1234abcd"}
"""

from __future__ import annotations

import logging
import threading
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

_log = logging.getLogger(__name__)

_lock = threading.Lock()
_store: dict[str, "_CheckpointEntry"] = {}


class _CheckpointEntry:
    __slots__ = ("source_name", "cursor", "run_id", "updated_at")

    def __init__(self, source_name: str, cursor: Any, run_id: int) -> None:
        self.source_name = source_name
        self.cursor = cursor
        self.run_id = run_id
        self.updated_at = datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def save(source_name: str, cursor: Any, *, run_id: int) -> None:
    """Save (or overwrite) the checkpoint cursor for *source_name*."""
    with _lock:
        _store[source_name] = _CheckpointEntry(
            source_name=source_name,
            cursor=deepcopy(cursor),
            run_id=run_id,
        )
    _log.debug(
        "checkpoint.saved source=%s run_id=%d cursor=%r", source_name, run_id, cursor
    )


def load(source_name: str) -> Any | None:
    """Return the stored cursor for *source_name*, or *None* if not present."""
    with _lock:
        entry = _store.get(source_name)
    if entry is None:
        return None
    return deepcopy(entry.cursor)


def clear(source_name: str) -> None:
    """Remove the checkpoint for *source_name* (called on successful completion)."""
    with _lock:
        removed = _store.pop(source_name, None)
    if removed is not None:
        _log.debug("checkpoint.cleared source=%s", source_name)


def clear_all() -> None:
    """Remove all checkpoints (e.g. during process shutdown or test teardown)."""
    with _lock:
        _store.clear()


def list_active() -> list[dict[str, Any]]:
    """Return a snapshot of all active checkpoints for health / debug endpoints."""
    with _lock:
        return [
            {
                "source_name": e.source_name,
                "cursor": deepcopy(e.cursor),
                "run_id": e.run_id,
                "updated_at": e.updated_at.isoformat(),
            }
            for e in _store.values()
        ]
