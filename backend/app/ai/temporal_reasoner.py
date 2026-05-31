"""Chronological ordering and gap detection for entity claims/events.

All logic is deterministic — no LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models.entities import MemoryClaim

# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TemporalGap:
    """A detected gap between two consecutive events."""

    after_claim_id: Optional[int]
    before_claim_id: Optional[int]
    gap_days: int


@dataclass
class TemporalSequence:
    """Chronologically ordered events for an entity."""

    entity_id: int
    events: list[dict]  # list of {claim_id, claim_type, timestamp, claim_value}
    gaps: list[TemporalGap]
    span_days: Optional[int]  # total span from first to last event


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _extract_timestamp(claim: MemoryClaim) -> Optional[datetime]:
    """Best-effort timestamp extraction from a claim."""
    # Prefer last_seen_at > updated_at > created_at
    for attr in ("last_seen_at", "updated_at", "created_at"):
        val = getattr(claim, attr, None)
        if val is not None:
            if isinstance(val, datetime):
                return val
    return None


def _to_event(claim: MemoryClaim) -> dict:
    return {
        "claim_id": claim.id,
        "claim_type": claim.claim_type,
        "timestamp": _extract_timestamp(claim),
        "claim_value": claim.claim_value,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def build_sequence(db: Session, entity_id: int) -> TemporalSequence:
    """Fetch all active claims for *entity_id* and return ordered TemporalSequence."""
    claims: list[MemoryClaim] = (
        db.query(MemoryClaim)
        .filter(
            MemoryClaim.entity_id == entity_id,
            MemoryClaim.is_active.is_(True),
        )
        .all()
    )

    events = [_to_event(c) for c in claims]
    # Sort: events with timestamps first (ascending), then unknowns at end
    events.sort(
        key=lambda e: (
            e["timestamp"] is None,
            e["timestamp"] or datetime.min.replace(tzinfo=timezone.utc),
        )
    )

    gaps = detect_gaps(events)

    span_days: Optional[int] = None
    timestamped = [e for e in events if e["timestamp"] is not None]
    if len(timestamped) >= 2:
        delta = timestamped[-1]["timestamp"] - timestamped[0]["timestamp"]
        span_days = delta.days

    return TemporalSequence(
        entity_id=entity_id, events=events, gaps=gaps, span_days=span_days
    )


def detect_gaps(events: list[dict], min_gap_days: int = 30) -> list[TemporalGap]:
    """Identify silent periods of ≥ *min_gap_days* in an ordered event list."""
    timestamped = [e for e in events if e.get("timestamp") is not None]
    gaps: list[TemporalGap] = []
    for i in range(len(timestamped) - 1):
        a = timestamped[i]
        b = timestamped[i + 1]
        delta: timedelta = b["timestamp"] - a["timestamp"]
        if delta.days >= min_gap_days:
            gaps.append(
                TemporalGap(
                    after_claim_id=a.get("claim_id"),
                    before_claim_id=b.get("claim_id"),
                    gap_days=delta.days,
                )
            )
    return gaps


def is_chronologically_consistent(events: list[dict]) -> bool:
    """Return True if all timestamped events are in non-decreasing order."""
    timestamped = [e["timestamp"] for e in events if e.get("timestamp") is not None]
    for i in range(len(timestamped) - 1):
        if timestamped[i + 1] < timestamped[i]:
            return False
    return True
