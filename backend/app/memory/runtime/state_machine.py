"""Memory state machine — enforces valid claim lifecycle transitions.

Deterministic; no DB or I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from app.memory.runtime.claim_lifecycle import (
    ClaimStatus,
    ClaimTransition,
    LifecyclePolicy,
)


class StateMachineError(Exception):
    """Raised when an illegal transition is attempted."""


@dataclass
class _ClaimRecord:
    key: str
    status: ClaimStatus
    rebuilds_since_touch: int = 0
    rebuilds_since_invalidation: int = 0
    invalidation_reason: str | None = None


@dataclass
class MemoryStateMachine:
    """Manages in-memory lifecycle state for a collection of claims.

    The machine tracks each claim by its stable *claim_key* and enforces
    policy-governed transitions.  Persistence is the caller's concern.

    Attributes
    ----------
    policy:
        The :class:`LifecyclePolicy` governing automatic transitions.
    """

    policy: LifecyclePolicy = field(default_factory=LifecyclePolicy)
    _records: Dict[str, _ClaimRecord] = field(default_factory=dict, repr=False)
    _history: List[ClaimTransition] = field(default_factory=list, repr=False)

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(
        self, claim_key: str, initial_status: ClaimStatus = ClaimStatus.DRAFT
    ) -> None:
        """Register a new claim.  Raises ``ValueError`` if *claim_key* already exists."""
        if claim_key in self._records:
            raise ValueError(f"Claim '{claim_key}' is already registered")
        self._records[claim_key] = _ClaimRecord(key=claim_key, status=initial_status)

    def register_or_get(
        self, claim_key: str, initial_status: ClaimStatus = ClaimStatus.DRAFT
    ) -> ClaimStatus:
        """Register claim if new, otherwise return its current status."""
        if claim_key not in self._records:
            self.register(claim_key, initial_status)
        return self._records[claim_key].status

    # ------------------------------------------------------------------
    # Manual transitions
    # ------------------------------------------------------------------

    def transition(
        self, claim_key: str, to_status: ClaimStatus, reason: str = ""
    ) -> ClaimTransition:
        """Apply a manual transition.

        Raises
        ------
        KeyError
            If *claim_key* is not registered.
        StateMachineError
            If the transition is not permitted by policy.
        """
        record = self._get(claim_key)
        tx = ClaimTransition(
            from_status=record.status,
            to_status=to_status,
            reason=reason,
            claim_key=claim_key,
        )
        allowed = self.policy.allowed_transitions(record.status)
        if to_status not in allowed:
            raise StateMachineError(
                f"Transition {record.status!r} → {to_status!r} not allowed "
                f"for claim '{claim_key}' (policy: {allowed})"
            )
        record.status = to_status
        if to_status == ClaimStatus.INVALIDATED:
            record.invalidation_reason = reason
            record.rebuilds_since_invalidation = 0
        elif to_status == ClaimStatus.ACTIVE:
            record.rebuilds_since_touch = 0
        self._history.append(tx)
        return tx

    def activate(self, claim_key: str) -> ClaimTransition:
        """Convenience: transition claim to ACTIVE."""
        return self.transition(claim_key, ClaimStatus.ACTIVE, reason="activated")

    def invalidate(
        self, claim_key: str, reason: str = "invalidated"
    ) -> ClaimTransition:
        """Convenience: transition claim to INVALIDATED."""
        return self.transition(claim_key, ClaimStatus.INVALIDATED, reason=reason)

    # ------------------------------------------------------------------
    # Rebuild cycle
    # ------------------------------------------------------------------

    def advance_rebuild_cycle(self) -> List[ClaimTransition]:
        """Tick rebuild counters and apply automatic policy transitions.

        Returns the list of automatic transitions that occurred.
        """
        auto_transitions: List[ClaimTransition] = []
        for record in self._records.values():
            record.rebuilds_since_touch += 1
            if record.status == ClaimStatus.INVALIDATED:
                record.rebuilds_since_invalidation += 1

            # Active → Stale
            if record.status == ClaimStatus.ACTIVE and self.policy.should_go_stale(
                record.rebuilds_since_touch
            ):
                tx = ClaimTransition(
                    from_status=ClaimStatus.ACTIVE,
                    to_status=ClaimStatus.STALE,
                    reason="auto:stale_after_rebuilds",
                    claim_key=record.key,
                )
                record.status = ClaimStatus.STALE
                self._history.append(tx)
                auto_transitions.append(tx)

            # Invalidated → Archived
            elif (
                record.status == ClaimStatus.INVALIDATED
                and self.policy.should_archive(record.rebuilds_since_invalidation)
            ):
                tx = ClaimTransition(
                    from_status=ClaimStatus.INVALIDATED,
                    to_status=ClaimStatus.ARCHIVED,
                    reason="auto:archive_after_invalidated",
                    claim_key=record.key,
                )
                record.status = ClaimStatus.ARCHIVED
                self._history.append(tx)
                auto_transitions.append(tx)

        return auto_transitions

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def status_of(self, claim_key: str) -> ClaimStatus:
        """Return current status of *claim_key*."""
        return self._get(claim_key).status

    def claims_by_status(self, status: ClaimStatus) -> List[str]:
        """Return all claim keys with the given status."""
        return [r.key for r in self._records.values() if r.status == status]

    def history_for(self, claim_key: str) -> List[ClaimTransition]:
        """Return all transitions for *claim_key* in order."""
        return [tx for tx in self._history if tx.claim_key == claim_key]

    @property
    def all_transitions(self) -> List[ClaimTransition]:
        """Full transition history across all claims."""
        return list(self._history)

    @property
    def claim_count(self) -> int:
        return len(self._records)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _get(self, claim_key: str) -> _ClaimRecord:
        try:
            return self._records[claim_key]
        except KeyError:
            raise KeyError(
                f"Claim '{claim_key}' is not registered in the state machine"
            )
