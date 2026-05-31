"""Snapshot lifecycle state machine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, FrozenSet, List, Optional, Set, Tuple


class SnapshotState(str, Enum):
    """States in the evidence snapshot lifecycle."""

    PENDING = "pending"
    STORED = "stored"
    VERIFIED = "verified"
    EXPIRED = "expired"
    PURGED = "purged"


# Allowed transitions: from_state → set of allowed to_states
_ALLOWED: Dict[SnapshotState, FrozenSet[SnapshotState]] = {
    SnapshotState.PENDING: frozenset({SnapshotState.STORED}),
    SnapshotState.STORED: frozenset({SnapshotState.VERIFIED, SnapshotState.EXPIRED}),
    SnapshotState.VERIFIED: frozenset({SnapshotState.EXPIRED}),
    SnapshotState.EXPIRED: frozenset({SnapshotState.PURGED}),
    SnapshotState.PURGED: frozenset(),
}


class SnapshotTransitionError(Exception):
    """Raised when a state transition is not permitted."""

    def __init__(
        self,
        snapshot_id: int,
        from_state: SnapshotState,
        to_state: SnapshotState,
    ) -> None:
        super().__init__(
            f"Cannot transition snapshot {snapshot_id} from {from_state} to {to_state}"
        )
        self.snapshot_id = snapshot_id
        self.from_state = from_state
        self.to_state = to_state


@dataclass
class _SnapshotRecord:
    snapshot_id: int
    state: SnapshotState = SnapshotState.PENDING
    history: List[Tuple[SnapshotState, SnapshotState, str]] = field(
        default_factory=list
    )


class SnapshotLifecycle:
    """In-process state machine tracking snapshot lifecycle.

    All state transitions are validated against :data:`_ALLOWED`.  The
    lifecycle does **not** interact with the database.
    """

    def __init__(self) -> None:
        self._records: Dict[int, _SnapshotRecord] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, snapshot_id: int) -> None:
        """Register a new snapshot in the PENDING state.

        Silently ignores re-registration of an already-tracked snapshot.
        """
        if snapshot_id not in self._records:
            self._records[snapshot_id] = _SnapshotRecord(snapshot_id=snapshot_id)

    def is_registered(self, snapshot_id: int) -> bool:
        return snapshot_id in self._records

    # ------------------------------------------------------------------
    # Transitions
    # ------------------------------------------------------------------

    def transition(
        self,
        snapshot_id: int,
        to_state: SnapshotState,
        reason: str = "",
    ) -> None:
        """Move *snapshot_id* to *to_state*.

        Raises
        ------
        KeyError
            If *snapshot_id* is not registered.
        SnapshotTransitionError
            If the transition is not permitted.
        """
        record = self._records[snapshot_id]
        from_state = record.state
        if to_state not in _ALLOWED[from_state]:
            raise SnapshotTransitionError(snapshot_id, from_state, to_state)
        record.history.append((from_state, to_state, reason))
        record.state = to_state

    def store(self, snapshot_id: int, reason: str = "stored") -> None:
        self.transition(snapshot_id, SnapshotState.STORED, reason)

    def verify(self, snapshot_id: int, reason: str = "verified") -> None:
        self.transition(snapshot_id, SnapshotState.VERIFIED, reason)

    def expire(self, snapshot_id: int, reason: str = "expired") -> None:
        self.transition(snapshot_id, SnapshotState.EXPIRED, reason)

    def purge(self, snapshot_id: int, reason: str = "purged") -> None:
        self.transition(snapshot_id, SnapshotState.PURGED, reason)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def state_of(self, snapshot_id: int) -> Optional[SnapshotState]:
        """Return current state or None if not registered."""
        record = self._records.get(snapshot_id)
        return record.state if record else None

    def snapshots_by_state(self, state: SnapshotState) -> List[int]:
        """Return sorted list of snapshot IDs in *state*."""
        return sorted(sid for sid, rec in self._records.items() if rec.state == state)

    def history_for(
        self, snapshot_id: int
    ) -> List[Tuple[SnapshotState, SnapshotState, str]]:
        """Return the full transition history for *snapshot_id*."""
        record = self._records.get(snapshot_id)
        return list(record.history) if record else []

    def allowed_next_states(self, snapshot_id: int) -> FrozenSet[SnapshotState]:
        """Return the set of states *snapshot_id* can move to next."""
        state = self.state_of(snapshot_id)
        if state is None:
            return frozenset()
        return _ALLOWED[state]

    @property
    def total_registered(self) -> int:
        return len(self._records)

    def all_states(self) -> Dict[int, SnapshotState]:
        """Return a snapshot_id → state mapping for all tracked snapshots."""
        return {sid: rec.state for sid, rec in self._records.items()}
