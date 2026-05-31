"""Chain-of-custody tracking for evidence records.

Records every hand-off from ingestion → review → publication
so the full lineage of a public record can be reconstructed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class CustodyStage(str, Enum):
    ingested = "ingested"
    review_queued = "review_queued"
    review_approved = "review_approved"
    review_rejected = "review_rejected"
    published = "published"
    unpublished = "unpublished"
    quarantined = "quarantined"


@dataclass
class CustodyEvent:
    stage: CustodyStage
    actor_id: str | None
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    notes: str | None = None


@dataclass
class CustodyChain:
    entity_type: str  # "CrimeIncident" | "ReviewItem" | "SourceSnapshot"
    entity_id: str | int
    events: list[CustodyEvent] = field(default_factory=list)

    def advance(
        self,
        stage: CustodyStage,
        actor_id: str | None,
        notes: str | None = None,
    ) -> CustodyEvent:
        ev = CustodyEvent(stage=stage, actor_id=actor_id, notes=notes)
        self.events.append(ev)
        return ev

    def current_stage(self) -> CustodyStage | None:
        return self.events[-1].stage if self.events else None

    def to_dict(self) -> dict:
        return {
            "entity_type": self.entity_type,
            "entity_id": str(self.entity_id),
            "events": [
                {
                    "stage": e.stage.value,
                    "actor_id": e.actor_id,
                    "timestamp": e.timestamp.isoformat(),
                    "notes": e.notes,
                }
                for e in self.events
            ],
        }
