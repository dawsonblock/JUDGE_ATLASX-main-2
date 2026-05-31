"""Enforce immutability on evidence fields after first write.

Evidence records (SourceSnapshot, CrimeIncident) must never have their
hash or raw content silently overwritten.  This module provides write-time
guards that raise ``ImmutabilityError`` on violation attempts.
"""
from __future__ import annotations


class ImmutabilityError(ValueError):
    """Raised when a mutation would overwrite an immutable evidence field."""


IMMUTABLE_SNAPSHOT_FIELDS: frozenset[str] = frozenset(
    {"content_hash", "raw_content", "fetched_at", "source_url"}
)

IMMUTABLE_INCIDENT_FIELDS: frozenset[str] = frozenset(
    {"source_id", "external_id", "source_snapshot_id"}
)


def assert_snapshot_fields_immutable(
    existing: dict, proposed: dict, *, entity_id: str | int | None = None
) -> None:
    """Raise ImmutabilityError if any immutable field in *proposed* differs from *existing*."""
    for field in IMMUTABLE_SNAPSHOT_FIELDS:
        if field not in proposed:
            continue
        old_val = existing.get(field)
        new_val = proposed[field]
        if old_val is not None and old_val != new_val:
            raise ImmutabilityError(
                f"Cannot overwrite immutable snapshot field '{field}' "
                f"(entity_id={entity_id}): {old_val!r} → {new_val!r}"
            )


def assert_incident_fields_immutable(
    existing: dict, proposed: dict, *, entity_id: str | int | None = None
) -> None:
    """Raise ImmutabilityError if any immutable incident field would change."""
    for field in IMMUTABLE_INCIDENT_FIELDS:
        if field not in proposed:
            continue
        old_val = existing.get(field)
        new_val = proposed[field]
        if old_val is not None and old_val != new_val:
            raise ImmutabilityError(
                f"Cannot overwrite immutable incident field '{field}' "
                f"(entity_id={entity_id}): {old_val!r} → {new_val!r}"
            )
