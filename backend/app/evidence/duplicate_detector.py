"""Detect duplicate evidence records before insertion."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models.entities import CrimeIncident, SourceSnapshot


@dataclass
class DuplicateResult:
    is_duplicate: bool
    existing_id: int | None = None
    reason: str | None = None


def check_snapshot_duplicate(
    db: Session, content_hash: str
) -> DuplicateResult:
    """Return DuplicateResult if a snapshot with the same hash already exists."""
    existing = (
        db.query(SourceSnapshot.id)
        .filter(SourceSnapshot.content_hash == content_hash)
        .first()
    )
    if existing:
        return DuplicateResult(is_duplicate=True, existing_id=existing[0], reason="same_content_hash")
    return DuplicateResult(is_duplicate=False)


def check_incident_duplicate(
    db: Session, source_key: str, external_id: str
) -> DuplicateResult:
    """Return DuplicateResult if a CrimeIncident with same source+external_id exists."""
    existing = (
        db.query(CrimeIncident.id)
        .filter(
            CrimeIncident.source_name == source_key,
            CrimeIncident.external_id == external_id,
        )
        .first()
    )
    if existing:
        return DuplicateResult(is_duplicate=True, existing_id=existing[0], reason="same_source_external_id")
    return DuplicateResult(is_duplicate=False)
