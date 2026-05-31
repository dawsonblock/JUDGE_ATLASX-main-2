"""Rebuild scheduler — tracks when entity memory should be rebuilt.

Deterministic; no DB or I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class RebuildTrigger(str, Enum):
    """Reason a rebuild was requested."""

    MANUAL = "manual"
    SCHEDULED = "scheduled"
    DRIFT_DETECTED = "drift_detected"
    SOURCE_UPDATED = "source_updated"
    INVALIDATION = "invalidation"
    STARTUP = "startup"


@dataclass
class RebuildSchedule:
    """An entry in the rebuild schedule.

    Attributes
    ----------
    entity_id:
        Canonical entity identifier.
    trigger:
        Why the rebuild was scheduled.
    priority:
        Lower numbers run first (0 = highest priority).
    run_after_tick:
        The scheduler will only dispatch this entry once
        :attr:`RebuildScheduler.current_tick` >= *run_after_tick*.
    attempt:
        How many times this schedule entry has been retried.
    """

    entity_id: int
    trigger: RebuildTrigger = RebuildTrigger.SCHEDULED
    priority: int = 5
    run_after_tick: int = 0
    attempt: int = 0

    def is_ready(self, current_tick: int) -> bool:
        return current_tick >= self.run_after_tick


class RebuildScheduler:
    """Manages a priority queue of pending entity rebuilds.

    All state is in-process; the scheduler does not persist anything.
    """

    def __init__(self, max_retries: int = 3, retry_delay_ticks: int = 2) -> None:
        self._max_retries = max_retries
        self._retry_delay_ticks = retry_delay_ticks
        self._pending: List[RebuildSchedule] = []
        self._in_flight: Dict[int, RebuildSchedule] = {}
        self._completed: List[int] = []
        self._failed: List[RebuildSchedule] = []
        self._tick: int = 0

    # ------------------------------------------------------------------
    # Tick
    # ------------------------------------------------------------------

    def advance_tick(self, by: int = 1) -> int:
        self._tick += by
        return self._tick

    @property
    def current_tick(self) -> int:
        return self._tick

    # ------------------------------------------------------------------
    # Scheduling
    # ------------------------------------------------------------------

    def schedule(
        self,
        entity_id: int,
        trigger: RebuildTrigger = RebuildTrigger.SCHEDULED,
        priority: int = 5,
        delay_ticks: int = 0,
    ) -> RebuildSchedule:
        """Add *entity_id* to the rebuild queue.

        If the entity is already scheduled (and not in-flight), the
        existing entry's priority is updated if the new priority is
        higher (lower number).
        """
        run_after = self._tick + delay_ticks

        # Promote existing pending entry?
        for existing in self._pending:
            if existing.entity_id == entity_id:
                if priority < existing.priority:
                    existing.priority = priority
                    existing.trigger = trigger
                    existing.run_after_tick = min(existing.run_after_tick, run_after)
                return existing

        sched = RebuildSchedule(
            entity_id=entity_id,
            trigger=trigger,
            priority=priority,
            run_after_tick=run_after,
        )
        self._pending.append(sched)
        return sched

    def schedule_many(
        self,
        entity_ids: List[int],
        trigger: RebuildTrigger = RebuildTrigger.SCHEDULED,
        priority: int = 5,
    ) -> List[RebuildSchedule]:
        return [self.schedule(eid, trigger, priority) for eid in entity_ids]

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def next_ready(self) -> RebuildSchedule | None:
        """Pop the highest-priority ready entry and mark it in-flight.

        Returns None if no entry is ready at the current tick.
        """
        ready = [s for s in self._pending if s.is_ready(self._tick)]
        if not ready:
            return None
        # Lowest priority number first; break ties by entity_id for determinism.
        best = min(ready, key=lambda s: (s.priority, s.entity_id))
        self._pending.remove(best)
        self._in_flight[best.entity_id] = best
        return best

    def drain_ready(self) -> List[RebuildSchedule]:
        """Return all ready entries, sorted by priority, all marked in-flight."""
        results: List[RebuildSchedule] = []
        while True:
            nxt = self.next_ready()
            if nxt is None:
                break
            results.append(nxt)
        return results

    # ------------------------------------------------------------------
    # Completion / failure
    # ------------------------------------------------------------------

    def complete(self, entity_id: int) -> bool:
        """Mark an in-flight rebuild as completed.  Returns True on success."""
        if entity_id not in self._in_flight:
            return False
        del self._in_flight[entity_id]
        self._completed.append(entity_id)
        return True

    def fail(self, entity_id: int, reason: str = "") -> Optional[RebuildSchedule]:
        """Mark an in-flight rebuild as failed.

        If retry budget remains, re-queues the entry with a backoff delay.
        Returns the re-queued schedule (or None if retries exhausted).
        """
        entry = self._in_flight.pop(entity_id, None)
        if entry is None:
            return None
        entry.attempt += 1
        if entry.attempt <= self._max_retries:
            entry.run_after_tick = self._tick + self._retry_delay_ticks * entry.attempt
            self._pending.append(entry)
            return entry
        self._failed.append(entry)
        return None

    # ------------------------------------------------------------------
    # Introspection
    # ------------------------------------------------------------------

    @property
    def pending_count(self) -> int:
        return len(self._pending)

    @property
    def in_flight_count(self) -> int:
        return len(self._in_flight)

    @property
    def completed_count(self) -> int:
        return len(self._completed)

    @property
    def failed_count(self) -> int:
        return len(self._failed)

    def is_pending(self, entity_id: int) -> bool:
        return any(s.entity_id == entity_id for s in self._pending)

    def is_in_flight(self, entity_id: int) -> bool:
        return entity_id in self._in_flight

    def stats(self) -> dict[str, int]:
        return {
            "pending": self.pending_count,
            "in_flight": self.in_flight_count,
            "completed": self.completed_count,
            "failed": self.failed_count,
        }
