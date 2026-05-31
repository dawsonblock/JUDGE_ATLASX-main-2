"""Temporal edge chain reconstruction.

Reconstructs time-ordered sequences of EdgeRecord objects from the
``entity_graph_edges`` table.  All queries are read-only; no writes.

Usage::

    chain = TemporalChain(db)
    active_now = chain.get_current("judge", 42)
    at_date    = chain.get_active_at("judge", 42, at=some_datetime)
    full_hist  = chain.get_timeline("judge", 42)

No LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.graph.edge_models import EdgeRecord, EdgeKey


def _row_to_edge_record(row) -> EdgeRecord:
    """Convert an EntityGraphEdge ORM row to an EdgeRecord dataclass."""
    return EdgeRecord(
        id=row.id,
        subject_type=row.subject_type,
        subject_id=row.subject_id,
        predicate=row.predicate,
        object_type=row.object_type,
        object_id=row.object_id,
        evidence_refs=row.evidence_refs,
        valid_from=row.valid_from,
        valid_until=row.valid_until,
        status=row.status,
        created_by=row.created_by,
    )


@dataclass
class TemporalEdge:
    """An EdgeRecord enriched with its explicit validity window."""

    edge: EdgeRecord
    valid_from: datetime
    valid_until: datetime | None

    @property
    def is_open(self) -> bool:
        """True if the edge has no defined end date."""
        return self.valid_until is None

    def is_active_at(self, at: datetime) -> bool:
        """Return True if this edge was active at the given instant."""
        return self.edge.is_active_at(at)


class TemporalChain:
    """Reconstructs time-ordered edge sequences for a given entity.

    An entity participates in edges either as *subject* or *object*.
    All three query helpers return edges ordered by ``valid_from`` ascending.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    # ------------------------------------------------------------------ #
    # Public interface
    # ------------------------------------------------------------------ #

    def get_timeline(
        self,
        entity_type: str,
        entity_id: int,
        status: str | None = None,
    ) -> list[TemporalEdge]:
        """Return the full chronological edge history for an entity.

        Args:
            entity_type: ORM entity_type string (e.g. ``"judge"``).
            entity_id:   Primary key.
            status:      Optionally filter by edge status
                         (``"active"``, ``"disputed"``, ``"retracted"``).

        Returns:
            List of TemporalEdge ordered oldest-first.
        """
        from app.models.entities import EntityGraphEdge  # lazy import

        q = self._base_query(entity_type, entity_id)
        if status is not None:
            q = q.filter(EntityGraphEdge.status == status)
        q = q.order_by(EntityGraphEdge.valid_from.asc())

        return [
            TemporalEdge(
                edge=_row_to_edge_record(row),
                valid_from=row.valid_from,
                valid_until=row.valid_until,
            )
            for row in q.all()
        ]

    def get_active_at(
        self,
        entity_type: str,
        entity_id: int,
        at: datetime,
    ) -> list[TemporalEdge]:
        """Return edges that were active at a specific point in time.

        An edge is active at ``at`` if:
        - ``valid_from  <= at``
        - ``valid_until >  at``  OR  ``valid_until IS NULL``

        Args:
            entity_type: ORM entity_type string.
            entity_id:   Primary key.
            at:          Datetime to evaluate (UTC recommended).

        Returns:
            List of TemporalEdge ordered oldest-first.
        """
        from app.models.entities import EntityGraphEdge  # lazy import

        q = (
            self._base_query(entity_type, entity_id)
            .filter(EntityGraphEdge.status == "active")
            .filter(EntityGraphEdge.valid_from <= at)
            .filter(
                or_(
                    EntityGraphEdge.valid_until == None,  # noqa: E711
                    EntityGraphEdge.valid_until > at,
                )
            )
            .order_by(EntityGraphEdge.valid_from.asc())
        )

        return [
            TemporalEdge(
                edge=_row_to_edge_record(row),
                valid_from=row.valid_from,
                valid_until=row.valid_until,
            )
            for row in q.all()
        ]

    def get_current(
        self,
        entity_type: str,
        entity_id: int,
    ) -> list[TemporalEdge]:
        """Return edges that are currently active (as of now, UTC).

        Convenience wrapper around :meth:`get_active_at`.

        Args:
            entity_type: ORM entity_type string.
            entity_id:   Primary key.

        Returns:
            List of TemporalEdge ordered oldest-first.
        """
        return self.get_active_at(
            entity_type,
            entity_id,
            at=datetime.now(timezone.utc),
        )

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    def _base_query(self, entity_type: str, entity_id: int):
        """Build base query matching entity as subject OR object."""
        from app.models.entities import EntityGraphEdge  # lazy import

        return self.db.query(EntityGraphEdge).filter(
            or_(
                (EntityGraphEdge.subject_type == entity_type)
                & (EntityGraphEdge.subject_id == entity_id),
                (EntityGraphEdge.object_type == entity_type)
                & (EntityGraphEdge.object_id == entity_id),
            )
        )
