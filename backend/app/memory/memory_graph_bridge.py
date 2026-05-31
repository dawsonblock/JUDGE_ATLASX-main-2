"""Memory → Graph synchronisation bridge.

Translates active :class:`~app.models.entities.MemoryClaim` rows for a
:class:`~app.models.entities.CanonicalEntity` into
:class:`~app.models.entities.EntityGraphEdge` S-P-O triples.

Design constraints
------------------
* **No ``db.commit()``** — the caller (``rebuild.run_rebuild``) owns the
  transaction and will commit when the whole rebuild loop finishes.
* **Idempotent** — a pre-insert existence check prevents duplicate edges.
  The unique constraint on the table provides a secondary safety net.
* **Claim-type → predicate mapping** is explicit and conservative: only
  claim types that carry a meaningful relational assertion become edges.
  Unknown claim types are silently skipped so that new claim types in
  ``extract_claims`` never crash the graph pipeline.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.models.entities import EntityGraphEdge, MemoryClaim

if TYPE_CHECKING:  # pragma: no cover
    pass

_log = logging.getLogger(__name__)

# Map claim_type → (predicate, object_type_field)
# object_type_field: the attribute on the claim whose value is used as
# the *string* object_type in the edge.  For self-referential claims the
# object_type mirrors the subject_type ("canonical_entity").
#
# Layout: claim_type → predicate string
# The subject is always ("canonical_entity", entity_id).
# For claim types that point to another entity the object_type is derived
# from the claim itself (e.g. a "role" claim links to "canonical_entity").
_CLAIM_PREDICATE: dict[str, str] = {
    "name_mention": "has_alias",
    "role": "has_role",
    "location": "located_in",
    "affiliation": "affiliated_with",
    "title": "holds_title",
}

# For all currently mapped claim types the object is another canonical
# entity identified by its *claim_value* interpreted as an entity id or
# name token.  We default to a synthetic "value_node" type so that the
# edge can be written without a fully-resolved object ID.
_DEFAULT_OBJECT_TYPE = "value_node"


def sync_claims_to_graph(
    entity_id: int,
    active_claims: list[MemoryClaim],
    db: Session,
) -> int:
    """Upsert :class:`EntityGraphEdge` rows derived from *active_claims*.

    Each mapped claim type produces one edge:
    ``(canonical_entity, entity_id) --predicate--> (value_node, claim.id)``

    Using ``claim.id`` as the object_id keeps the object reference stable
    and unique without needing to resolve a separate entity record for
    every claim value.  Callers that want richer graph topology can later
    re-link edges via an admin tool.

    Args:
        entity_id:     The :class:`CanonicalEntity` id acting as graph subject.
        active_claims: Active :class:`MemoryClaim` rows for this entity.
        db:            Open SQLAlchemy session.  **No commit is issued.**

    Returns:
        Number of new edges inserted.
    """
    inserted = 0
    now = datetime.now(timezone.utc)

    for claim in active_claims:
        if not claim.is_active:
            continue  # caller should pre-filter, but guard defensively

        predicate = _CLAIM_PREDICATE.get(claim.claim_type)
        if predicate is None:
            continue  # claim type not mapped → skip silently

        object_type = _DEFAULT_OBJECT_TYPE
        object_id = claim.id  # stable unique id; no FK required

        # --- idempotency check -------------------------------------------
        existing = (
            db.query(EntityGraphEdge)
            .filter(
                EntityGraphEdge.subject_type == "canonical_entity",
                EntityGraphEdge.subject_id == entity_id,
                EntityGraphEdge.predicate == predicate,
                EntityGraphEdge.object_type == object_type,
                EntityGraphEdge.object_id == object_id,
            )
            .first()
        )
        if existing is not None:
            continue  # already written; no-op

        edge = EntityGraphEdge(
            subject_type="canonical_entity",
            subject_id=entity_id,
            predicate=predicate,
            object_type=object_type,
            object_id=object_id,
            source_snapshot_id=claim.source_snapshot_id,
            evidence_refs=[
                {
                    "claim_id": claim.id,
                    "claim_type": claim.claim_type,
                    "confidence": claim.confidence,
                }
            ],
            created_by="memory_rebuild",
            status="active",
            valid_from=now,
        )
        db.add(edge)
        db.flush()  # assign id without committing — caller owns transaction
        inserted += 1
        _log.debug(
            "graph_bridge.edge_created entity_id=%d claim_id=%d predicate=%s",
            entity_id,
            claim.id,
            predicate,
        )

    return inserted
