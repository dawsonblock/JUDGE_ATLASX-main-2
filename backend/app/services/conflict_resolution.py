"""Source trust-tier conflict resolution service.

When two sources attempt to contribute data for the same entity, this module
enforces the invariant:

    *A lower-trust source must never silently overwrite a value contributed
    by a higher-trust source.*

Public API
----------
detect_conflicts(db, incoming, incoming_source_id) → list[dict]
    Return a list of zero or more conflict descriptors.  One dict per field
    where the incoming source has a lower trust tier than the authoritative
    (existing) source.

record_conflict(conflict_data, db) → SourceTierConflict
    Persist one conflict descriptor as a ``SourceTierConflict`` audit row.

resolve_conflict(existing_value, incoming_value, existing_tier, incoming_tier)
    → tuple[str, str]
    Return (resolved_value, resolution_label) where resolution_label is one of
    ``"kept_existing"`` | ``"accepted_incoming"`` | ``"merged"``.

Trust tier ordering is delegated to
:func:`app.services.publish_rules.numeric_trust_tier` so that both modules
share a single source-of-truth for tier weights.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.services.publish_rules import numeric_trust_tier

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.ingestion.adapters import ParsedRecord
    from app.models.entities import SourceRegistry, SourceTierConflict


# ---------------------------------------------------------------------------
# Fields inspected during conflict detection.
# Extend as new entity shapes are added to the pipeline.
# ---------------------------------------------------------------------------

_CONFLICT_FIELDS: tuple[str, ...] = (
    "title",
    "summary",
    "docket_text",
    "entry_description",
    "source_quality",
    "judge_name",
    "case_name",
    "caption",
)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def detect_conflicts(
    db: "Session",
    incoming: "ParsedRecord",
    incoming_source_id: int,
) -> list[dict[str, Any]]:
    """Return conflict descriptors for fields where the incoming source has a
    lower trust tier than the authoritative source that contributed the
    existing event.

    A conflict descriptor is a plain dict with keys::

        incoming_source_id    int
        authoritative_source_id  int  (sourced from the existing LegalSource)
        entity_type           str  ("event" | "case" | …)
        entity_id             int | None
        field_name            str
        existing_value        str | None
        incoming_value        str | None
        resolution            str
        resolution_reason     str | None

    If no matching existing event is found for the incoming record's docket
    number then an empty list is returned (no conflict possible).

    This function is **read-only**: it does not write to the database.
    """
    from app.models.entities import Event, LegalSource, SourceRegistry  # local import

    # Resolve incoming source tier from SourceRegistry
    incoming_registry: SourceRegistry | None = (
        db.query(SourceRegistry).filter_by(id=incoming_source_id).first()
    )
    if incoming_registry is None:
        return []

    incoming_tier_num = numeric_trust_tier(incoming_registry.source_tier)

    if not incoming.docket_number:
        return []

    # Find any existing event whose case shares this docket number
    from sqlalchemy import select

    from app.models.entities import Case

    existing_case: Case | None = db.scalar(
        select(Case).where(Case.docket_number == incoming.docket_number).limit(1)
    )
    if existing_case is None:
        return []

    # Fetch all events linked to this case
    existing_events: list[Event] = (
        db.query(Event).filter_by(case_id=existing_case.id).all()
    )
    if not existing_events:
        return []

    conflicts: list[dict[str, Any]] = []

    for event in existing_events:
        # Determine the trust tier of the source that wrote the existing event
        # by looking at its EventSources join rows, then at the SourceRegistry.
        from app.models.entities import EventSource

        event_sources: list[EventSource] = (
            db.query(EventSource).filter_by(event_id=event.event_id).all()
        )
        if not event_sources:
            # No source attribution → cannot determine tier; skip
            continue

        for es in event_sources:
            legal_src: LegalSource | None = (
                db.query(LegalSource).filter_by(id=es.source_id).first()
            )
            if legal_src is None:
                continue

            # Match the legal source to a SourceRegistry row by source_key
            auth_registry: SourceRegistry | None = (
                db.query(SourceRegistry)
                .filter_by(source_key=legal_src.source_key)
                .first()
            )
            if auth_registry is None:
                continue

            auth_tier_num = numeric_trust_tier(auth_registry.source_tier)

            if incoming_tier_num >= auth_tier_num:
                # Incoming is at least as trusted; no conflict
                continue

            # Incoming is lower-trust — check each field for a non-trivial diff
            for field in _CONFLICT_FIELDS:
                incoming_val = getattr(incoming, field, None)
                existing_val = getattr(event, field, None)
                if incoming_val is None or existing_val is None:
                    continue
                if str(incoming_val).strip() == str(existing_val).strip():
                    continue

                resolved_value, resolution = resolve_conflict(
                    existing_value=str(existing_val),
                    incoming_value=str(incoming_val),
                    existing_tier=auth_tier_num,
                    incoming_tier=incoming_tier_num,
                )
                conflicts.append(
                    {
                        "incoming_source_id": incoming_source_id,
                        "authoritative_source_id": auth_registry.id,
                        "entity_type": "event",
                        "entity_id": None,  # event PK is a string event_id; omit
                        "field_name": field,
                        "existing_value": str(existing_val),
                        "incoming_value": str(incoming_val),
                        "resolution": resolution,
                        "resolution_reason": (
                            f"Authoritative source '{auth_registry.source_key}' "
                            f"(tier {auth_tier_num}) outranks incoming source "
                            f"'{incoming_registry.source_key}' (tier {incoming_tier_num})."
                        ),
                    }
                )

    return conflicts


def record_conflict(
    conflict_data: dict[str, Any],
    db: "Session",
) -> "SourceTierConflict":
    """Persist a single conflict descriptor as a ``SourceTierConflict`` row.

    The row is flushed (not committed) so the caller controls transaction
    boundaries.
    """
    from app.models.entities import SourceTierConflict  # local import

    conflict = SourceTierConflict(
        incoming_source_id=conflict_data["incoming_source_id"],
        authoritative_source_id=conflict_data["authoritative_source_id"],
        entity_type=conflict_data.get("entity_type", "unknown"),
        entity_id=conflict_data.get("entity_id"),
        field_name=conflict_data["field_name"],
        existing_value=conflict_data.get("existing_value"),
        incoming_value=conflict_data.get("incoming_value"),
        resolution=conflict_data.get("resolution", "kept_existing"),
        resolution_reason=conflict_data.get("resolution_reason"),
    )
    db.add(conflict)
    db.flush()
    return conflict


def resolve_conflict(
    existing_value: str,
    incoming_value: str,
    existing_tier: int,
    incoming_tier: int,
) -> tuple[str, str]:
    """Determine the winning value and return ``(winning_value, resolution_label)``.

    Resolution rules:
    - ``incoming_tier  < existing_tier``  → keep existing  (``"kept_existing"``)
    - ``incoming_tier  > existing_tier``  → accept incoming (``"accepted_incoming"``)
    - ``incoming_tier == existing_tier``  → keep existing   (``"kept_existing"``)
      Equal-tier conflicts are deferred to human review by default; the record
      is still written to the audit table so operators can see the diff.

    Returns a 2-tuple: (resolved_value, resolution_label).
    """
    if incoming_tier > existing_tier:
        return incoming_value, "accepted_incoming"
    return existing_value, "kept_existing"
