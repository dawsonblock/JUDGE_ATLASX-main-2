"""Canonical publication policy for public domain records.

ReviewItem workflow decisions are intentionally separate from entity
publication.  A ReviewItem can be ``approved`` for internal promotion without
making any Event, CrimeIncident, LegalSource, LegalInstrument, or
RelationshipEvidence public.  Public entities require a domain review status,
public visibility, and an evidence anchor checked here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.entities import (
    CrimeIncident,
    Event,
    LegalInstrument,
    LegalSource,
    RelationshipEvidence,
    SourceRegistry,
    SourceSnapshot,
)
from app.policies.state_model import (
    PublicationState,
    normalize_review_decision,
    publication_state_for_review_status,
)
from sqlalchemy.orm import Session

PENDING_REVIEW = "pending_review"
VERIFIED_COURT_RECORD = "verified_court_record"
OFFICIAL_POLICE_OPEN_DATA_REPORT = "official_police_open_data_report"
OFFICIAL_STATISTICS_AGGREGATE = "official_statistics_aggregate"
NEWS_ONLY_CONTEXT = "news_only_context"
CORRECTED = "corrected"
DISPUTED = "disputed"
REJECTED = "rejected"
REMOVED_FROM_PUBLIC = "removed_from_public"

# Conservative choice: news-only context is not a public map/court/incident fact.
PUBLIC_REVIEW_STATUSES = {
    VERIFIED_COURT_RECORD,
    OFFICIAL_POLICE_OPEN_DATA_REPORT,
    OFFICIAL_STATISTICS_AGGREGATE,
    CORRECTED,
}
NON_PUBLIC_REVIEW_STATUSES = {
    PENDING_REVIEW,
    NEWS_ONLY_CONTEXT,
    DISPUTED,
    REJECTED,
    REMOVED_FROM_PUBLIC,
}
REVIEW_STATUSES = PUBLIC_REVIEW_STATUSES | NON_PUBLIC_REVIEW_STATUSES

UNSAFE_MAP_PRECISIONS = frozenset(
    {
        "exact_private_address",
        "exact_residence",
        "home_address",
        "exact_address",
        "private_residence",
        "rooftop",
        "parcel",
        "residential",
        "exact",
        "address_level",
    }
)


@dataclass(frozen=True)
class PublicationDecision:
    allowed: bool
    reasons: list[str]
    public_status: str | None = None
    public_visibility_value: bool | str | None = None


def entity_review_status(entity: Any) -> str | None:
    status = getattr(entity, "review_status", None)
    return str(status) if status is not None else None


def canonical_publication_state(entity: Any) -> PublicationState:
    """Return canonical publication lifecycle state for *entity*.

    This adapter keeps existing ``review_status`` and visibility fields intact
    while giving callers a typed state model for newer flows.
    """
    return publication_state_for_review_status(
        entity_review_status(entity),
        entity_public_visibility(entity),
    )


_NON_PUBLIC_RELATIONSHIP_STATES: frozenset[str] = frozenset(
    {"rejected", "disputed", "removed", "removed_from_public"}
)
_PENDING_RELATIONSHIP_STATES: frozenset[str] = frozenset(
    {"pending", "pending_review", "review_required", "unverified", "unknown"}
)
_ACTIVE_RELATIONSHIP_STATES: frozenset[str] = frozenset(
    {"verified", "approved", "active"}
)


def relationship_public_status(entity: Any) -> str:
    """Derive a canonical review status from RelationshipEvidence workflow fields.

    Used at record-promotion time to set the ``review_status`` column.
    The column is the authoritative publication gate; this function is the
    upgrade path only — it must not be used as a runtime bypass.
    """
    verification = getattr(entity, "verification_status", None)
    relationship = getattr(entity, "relationship_status", None)
    if (
        verification in _NON_PUBLIC_RELATIONSHIP_STATES
        or relationship in _NON_PUBLIC_RELATIONSHIP_STATES
    ):
        return REJECTED
    if verification == "verified" and relationship in ("verified", "approved"):
        return VERIFIED_COURT_RECORD
    if verification == "reviewed":
        return OFFICIAL_POLICE_OPEN_DATA_REPORT
    return PENDING_REVIEW


def _relationship_policy_reasons(entity: Any) -> list[str]:
    reasons: list[str] = []
    verification = str(getattr(entity, "verification_status", "") or "").lower()
    relationship = str(getattr(entity, "relationship_status", "") or "").lower()

    if verification in _NON_PUBLIC_RELATIONSHIP_STATES:
        reasons.append(f"relationship_verification_blocked:{verification}")
    if relationship in _NON_PUBLIC_RELATIONSHIP_STATES:
        reasons.append(f"relationship_status_blocked:{relationship}")

    if verification in _PENDING_RELATIONSHIP_STATES:
        reasons.append(f"relationship_verification_pending:{verification}")
    if relationship in _PENDING_RELATIONSHIP_STATES:
        reasons.append(f"relationship_status_pending:{relationship}")

    if verification == "verified" and relationship not in _ACTIVE_RELATIONSHIP_STATES:
        reasons.append(
            f"relationship_status_incompatible_with_verified:{relationship or 'missing'}"
        )

    if verification == "reviewed" and relationship in _NON_PUBLIC_RELATIONSHIP_STATES:
        reasons.append(f"relationship_reviewed_but_blocked:{relationship}")

    if not verification:
        reasons.append("relationship_verification_missing")
    if not relationship:
        reasons.append("relationship_status_missing")

    return reasons


def entity_public_visibility(entity: Any) -> bool:
    if isinstance(entity, CrimeIncident) or hasattr(entity, "is_public"):
        value = getattr(entity, "is_public", False)
    else:
        value = getattr(entity, "public_visibility", False)
    if value is True:
        return True
    if value is False or value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() == "public"
    return False


def set_entity_public_visibility(entity: Any, visible: bool) -> None:
    if isinstance(entity, CrimeIncident):
        entity.is_public = bool(visible)
    elif isinstance(entity, LegalInstrument):
        entity.public_visibility = "public" if visible else "private"
    else:
        entity.public_visibility = bool(visible)


def _snapshot_has_hash(db: Session, snapshot_id: int | None) -> tuple[bool, list[str]]:
    if snapshot_id is None:
        return False, ["missing_evidence_snapshot_id"]
    snapshot = db.get(SourceSnapshot, snapshot_id)
    if snapshot is None:
        return False, ["evidence_snapshot_not_found"]
    if not snapshot.content_hash:
        return False, ["missing_evidence_content_hash"]
    return True, []


def _prefix_snapshot_reasons(reasons: list[str], prefix: str) -> list[str]:
    return [
        reason.replace("evidence_snapshot", f"{prefix}_snapshot").replace(
            "evidence_content_hash", f"{prefix}_snapshot_content_hash"
        )
        for reason in reasons
    ]


def evidence_anchor_status(
    db: Session,
    entity_type: str,
    entity: Any,
) -> tuple[bool, list[str]]:
    if entity_type == "event" or isinstance(entity, Event):
        for link in getattr(entity, "source_links", []) or []:
            source = getattr(link, "source", None)
            if (
                source
                and getattr(source, "url", None)
                and getattr(source, "url_hash", None)
                and entity_review_status(source) in PUBLIC_REVIEW_STATUSES
                and entity_public_visibility(source)
            ):
                return True, []
        return False, ["event_missing_public_reviewed_source_link"]

    if entity_type == "crime_incident" or isinstance(entity, CrimeIncident):
        ok, reasons = _snapshot_has_hash(
            db, getattr(entity, "source_snapshot_id", None)
        )
        return ok, _prefix_snapshot_reasons(reasons, "source")

    if entity_type in {"source", "legal_source"} or isinstance(entity, LegalSource):
        reasons: list[str] = []
        if not getattr(entity, "url", None):
            reasons.append("legal_source_missing_url")
        if not getattr(entity, "url_hash", None):
            reasons.append("legal_source_missing_url_hash")
        return len(reasons) == 0, reasons

    if entity_type == "legal_instrument" or isinstance(entity, LegalInstrument):
        ok, reasons = _snapshot_has_hash(db, getattr(entity, "raw_snapshot_id", None))
        return ok, _prefix_snapshot_reasons(reasons, "raw")

    if entity_type == "relationship_evidence" or isinstance(
        entity, RelationshipEvidence
    ):
        return _snapshot_has_hash(db, getattr(entity, "evidence_snapshot_id", None))

    return False, [f"unknown_entity_type:{entity_type}"]


def _has_safe_location(entity_type: str, entity: Any) -> list[str]:
    reasons: list[str] = []
    if entity_type == "crime_incident" or isinstance(entity, CrimeIncident):
        if (
            getattr(entity, "latitude_public", None) is None
            or getattr(entity, "longitude_public", None) is None
        ):
            reasons.append("missing_public_coordinates")
        elif (
            getattr(entity, "latitude_public", 0.0) == 0.0
            or getattr(entity, "longitude_public", 0.0) == 0.0
        ):
            reasons.append("invalid_public_coordinates")
        precision = str(getattr(entity, "precision_level", "") or "").lower()
        if precision in UNSAFE_MAP_PRECISIONS or any(
            marker in precision
            for marker in ("exact", "address", "residence", "rooftop")
        ):
            reasons.append(f"unsafe_precision:{precision}")
    return reasons


def _source_registry_reasons(entity: Any) -> list[str]:
    source = getattr(entity, "source", None)
    if not isinstance(source, SourceRegistry):
        return []
    reasons: list[str] = []
    if source.source_class and source.source_class != "machine_ingest":
        reasons.append(f"source_not_machine_ingest:{source.source_class}")
    if source.automation_status and source.automation_status != "machine_ready_enabled":
        reasons.append(f"source_not_machine_ready_enabled:{source.automation_status}")
    if source.lifecycle_state and source.lifecycle_state != "runnable":
        reasons.append(f"source_not_runnable:{source.lifecycle_state}")
    if source.is_active is False:
        reasons.append("source_inactive")
    return reasons


def can_publish_entity(
    db: Session, entity_type: str, entity: Any
) -> PublicationDecision:
    status = entity_review_status(entity)
    reasons: list[str] = []
    if status not in REVIEW_STATUSES:
        reasons.append(f"unsupported_review_status:{status}")
    if status not in PUBLIC_REVIEW_STATUSES:
        reasons.append(f"non_public_review_status:{status}")

    evidence_ok, evidence_reasons = evidence_anchor_status(db, entity_type, entity)
    if not evidence_ok:
        reasons.extend(evidence_reasons)
    if entity_type == "relationship_evidence" or isinstance(entity, RelationshipEvidence):
        reasons.extend(_relationship_policy_reasons(entity))
    reasons.extend(_has_safe_location(entity_type, entity))
    reasons.extend(_source_registry_reasons(entity))

    allowed = len(reasons) == 0
    visibility_value: bool | str = (
        "public" if isinstance(entity, LegalInstrument) else True
    )
    return PublicationDecision(
        allowed=allowed,
        reasons=reasons,
        public_status=status if allowed else None,
        public_visibility_value=visibility_value if allowed else None,
    )


def can_show_public_entity(
    db_or_entity_type: Session | str,
    entity_type_or_entity: str | Any,
    entity: Any | None = None,
) -> PublicationDecision:
    if entity is None:
        db: Session | None = None
        entity_type = str(db_or_entity_type)
        entity = entity_type_or_entity
    else:
        db = db_or_entity_type  # type: ignore[assignment]
        entity_type = str(entity_type_or_entity)
    status = entity_review_status(entity)
    reasons: list[str] = []
    if status not in PUBLIC_REVIEW_STATUSES:
        reasons.append(f"non_public_review_status:{status}")
    if not entity_public_visibility(entity):
        reasons.append("public_visibility_false")
    if db is not None:
        evidence_ok, evidence_reasons = evidence_anchor_status(db, entity_type, entity)
        if not evidence_ok:
            reasons.extend(evidence_reasons)
    if entity_type == "relationship_evidence" or isinstance(entity, RelationshipEvidence):
        reasons.extend(_relationship_policy_reasons(entity))
    reasons.extend(_has_safe_location(entity_type, entity))
    if status == NEWS_ONLY_CONTEXT and entity_type in {
        "event",
        "crime_incident",
        "legal_instrument",
    }:
        reasons.append("context_only_not_public_fact")
    return PublicationDecision(
        allowed=len(reasons) == 0,
        reasons=reasons,
        public_status=status if len(reasons) == 0 else None,
        public_visibility_value=getattr(
            entity, "public_visibility", getattr(entity, "is_public", None)
        ),
    )


def public_status_for_decision(
    entity_type: str,
    decision: str | None,
    requested_status: str | None = None,
) -> str:
    if requested_status:
        return requested_status
    if decision in REVIEW_STATUSES:
        return str(decision)

    normalized_decision = normalize_review_decision(decision)
    if normalized_decision is None:
        return str(decision or "")

    if normalized_decision.value == "approve":
        if entity_type == "crime_incident":
            return OFFICIAL_POLICE_OPEN_DATA_REPORT
        return VERIFIED_COURT_RECORD
    if normalized_decision.value == "reject":
        return REJECTED
    if normalized_decision.value == "correct":
        return CORRECTED
    if normalized_decision.value == "dispute":
        return DISPUTED
    if normalized_decision.value == "remove":
        return REMOVED_FROM_PUBLIC
    return str(decision or "")
