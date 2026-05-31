"""Auto-linker: connects incident/event records to Cases/Judges via authoritative identifiers.

Linking hierarchy (by confidence):
  1. Normalized docket/file number match  → confidence 0.95, action="link"
  2. CourtListener docket ID match        → confidence 0.90, action="link"
  3. Name-only match                      → confidence 0.35, action="quarantine"

Only links with confidence >= _AUTO_LINK_THRESHOLD (0.85) are auto-published.
Name-only matches are never auto-linked; they require manual review.
All DB writes go through RelationshipEvidenceService.create_evidence().
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import Case
from app.services.relationship_evidence import RelationshipEvidenceService

# Minimum confidence for an auto-published link (docket or CL-ID match only)
_AUTO_LINK_THRESHOLD = 0.85


def _normalize_docket(raw: str) -> str:
    """Uppercase and strip whitespace/dashes for consistent comparisons."""
    return re.sub(r"[\s\-]+", "", raw).upper()


@dataclass
class LinkResult:
    """Result of an auto-link attempt."""

    action: str  # "link" | "quarantine" | "skip"
    confidence: float
    relationship_type: str | None
    evidence_id: int | None
    reasons: list[str] = field(default_factory=list)


def auto_link_by_docket(
    db: Session,
    from_entity_type: str,
    from_entity_id: int,
    docket_number: str,
    source_key: str,
    evidence_excerpt: str | None = None,
) -> LinkResult:
    """Link *from_entity* to a Case by normalised docket/file number.

    Returns action="link" at confidence 0.95 when exactly one Case matches.
    Returns action="quarantine" at confidence 0.35 when no match or ambiguous.
    """
    if not docket_number or not docket_number.strip():
        return LinkResult(
            action="skip",
            confidence=0.0,
            relationship_type=None,
            evidence_id=None,
            reasons=["empty_docket_number"],
        )

    norm = _normalize_docket(docket_number)
    cases = db.query(Case).filter(Case.normalized_docket_number == norm).all()

    if len(cases) == 1:
        case = cases[0]
        svc = RelationshipEvidenceService(db)
        try:
            ev = svc.create_evidence(
                from_entity_type=from_entity_type,
                from_entity_id=from_entity_id,
                to_entity_type="case",
                to_entity_id=case.id,
                relationship_type="linked_via_docket",
                evidence_type="docket_text",
                evidence_source=source_key,
                evidence_excerpt=evidence_excerpt,
                extracted_by="auto_linker",
                confidence=0.95,
            )
        except IntegrityError:
            db.rollback()
            return LinkResult(
                action="link",
                confidence=0.95,
                relationship_type="linked_via_docket",
                evidence_id=None,
                reasons=["duplicate_evidence_skipped"],
            )
        return LinkResult(
            action="link",
            confidence=0.95,
            relationship_type="linked_via_docket",
            evidence_id=ev.id,
            reasons=[f"docket_match:{norm}"],
        )

    if len(cases) > 1:
        return LinkResult(
            action="quarantine",
            confidence=0.35,
            relationship_type="linked_via_docket",
            evidence_id=None,
            reasons=[f"ambiguous_docket:{norm}", f"matched_count:{len(cases)}"],
        )

    return LinkResult(
        action="quarantine",
        confidence=0.35,
        relationship_type=None,
        evidence_id=None,
        reasons=[f"no_docket_match:{norm}"],
    )


def auto_link_by_courtlistener_id(
    db: Session,
    from_entity_type: str,
    from_entity_id: int,
    cl_docket_id: str | int,
    source_key: str,
    evidence_excerpt: str | None = None,
) -> LinkResult:
    """Link *from_entity* to a Case by CourtListener docket ID.

    Returns action="link" at confidence 0.90 on exact match.
    Returns action="quarantine" at confidence 0.35 when no match or ambiguous.
    """
    if cl_docket_id is None:
        return LinkResult(
            action="skip",
            confidence=0.0,
            relationship_type=None,
            evidence_id=None,
            reasons=["empty_cl_id"],
        )

    cl_id_str = str(cl_docket_id).strip()
    if not cl_id_str:
        return LinkResult(
            action="skip",
            confidence=0.0,
            relationship_type=None,
            evidence_id=None,
            reasons=["empty_cl_id"],
        )

    cases = db.query(Case).filter(Case.courtlistener_docket_id == cl_id_str).all()

    if len(cases) == 1:
        case = cases[0]
        svc = RelationshipEvidenceService(db)
        try:
            ev = svc.create_evidence(
                from_entity_type=from_entity_type,
                from_entity_id=from_entity_id,
                to_entity_type="case",
                to_entity_id=case.id,
                relationship_type="linked_via_docket",
                evidence_type="docket_text",
                evidence_source=source_key,
                evidence_excerpt=evidence_excerpt,
                extracted_by="auto_linker",
                confidence=0.90,
            )
        except IntegrityError:
            db.rollback()
            return LinkResult(
                action="link",
                confidence=0.90,
                relationship_type="linked_via_docket",
                evidence_id=None,
                reasons=["duplicate_evidence_skipped"],
            )
        return LinkResult(
            action="link",
            confidence=0.90,
            relationship_type="linked_via_docket",
            evidence_id=ev.id,
            reasons=[f"cl_id_match:{cl_id_str}"],
        )

    if len(cases) > 1:
        return LinkResult(
            action="quarantine",
            confidence=0.35,
            relationship_type="linked_via_docket",
            evidence_id=None,
            reasons=[f"ambiguous_cl_id:{cl_id_str}", f"matched_count:{len(cases)}"],
        )

    return LinkResult(
        action="quarantine",
        confidence=0.35,
        relationship_type=None,
        evidence_id=None,
        reasons=[f"no_cl_id_match:{cl_id_str}"],
    )


def auto_link_by_name_only(
    db: Session,
    from_entity_type: str,
    from_entity_id: int,
    name: str,
    source_key: str,
) -> LinkResult:
    """Name-only link — always quarantined; never auto-published.

    Name matches are inherently ambiguous and require manual review before
    a public relationship can be created.  *db* is accepted for API consistency
    but is not used.
    """
    preview = (name or "")[:60]
    return LinkResult(
        action="quarantine",
        confidence=0.35,
        relationship_type="same_incident",
        evidence_id=None,
        reasons=["name_only_match", f"name:{preview}"],
    )
