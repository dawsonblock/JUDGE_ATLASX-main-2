import hashlib
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.crime_sources.base import CrimeIncidentRecord
from app.ingestion.statuses import PENDING
from app.models.entities import CrimeIncident, ReviewItem
from app.services.auto_review import auto_review
from app.services.publish_rules import (
    TIER_BLOCK,
    resolve_publication_policy,
)

GENERALIZED_PRECISION_LEVELS = {
    "block",
    "intersection",
    "general_area",
    "neighbourhood_centroid",
    "neighborhood_centroid",
    "community_area_centroid",
    "police_beat_centroid",
    "district_centroid",
    "ward_centroid",
    "city_centroid",
    "province_centroid",
    "state_centroid",
    "country_centroid",
}
# Enhanced pattern to reject unsafe crime records
UNSAFE_NOTE_PATTERN = re.compile(
    r"\b(?:suspect|victim|address|residence|residing|dob|date of birth|"
    r"family|spouse|child|children|parent|relative|apartment|apt|"
    r"home|house|dwelling|phone|email|ssn|social security)\b",
    re.IGNORECASE,
)
RESIDENCE_PATTERN = re.compile(
    r"\b(?:residence|residing|home|house|dwelling|apartment|apt)\b",
    re.IGNORECASE,
)


class CrimeIncidentValidationError(ValueError):
    """Raised when a reported crime incident is unsafe for public map storage."""


def persist_crime_incident(
    db: Session,
    record: CrimeIncidentRecord,
    source_key: str | None = None,
    import_batch_hash: str | None = None,
    source_snapshot_id: int | None = None,
) -> CrimeIncident:
    _validate_record(record)
    external_id = record.external_id or derive_external_id(record)
    incident = db.scalar(
        select(CrimeIncident).where(
            CrimeIncident.source_name == record.source_name,
            CrimeIncident.external_id == external_id,
        )
    )
    if not incident:
        incident = CrimeIncident(
            source_name=record.source_name, external_id=external_id
        )
        db.add(incident)
        # New records always start as pending_review
        prev_review_status = "pending_review"
        is_new = True
    else:
        # Preserve existing review status unless safety fields changed
        prev_review_status = incident.review_status
        is_new = False

    # Track safety-sensitive changes
    safety_fields_changed = False
    if incident.id is not None:
        if (
            incident.incident_type != record.incident_type.strip()
            or incident.incident_category
            != normalize_incident_category(record.incident_category)
            or incident.public_area_label != _clean(record.public_area_label)
            or incident.latitude_public != record.latitude_public
            or incident.longitude_public != record.longitude_public
            or incident.notes != _clean(record.notes)
        ):
            safety_fields_changed = True

    incident.source_id = record.source_id
    incident.incident_type = record.incident_type.strip()
    incident.incident_category = normalize_incident_category(record.incident_category)
    incident.reported_at = record.reported_at
    incident.occurred_at = record.occurred_at
    incident.city = _clean(record.city)
    incident.province_state = _clean(record.province_state)
    incident.country = _clean(record.country)
    incident.public_area_label = _clean(record.public_area_label)
    incident.latitude_public = record.latitude_public
    incident.longitude_public = record.longitude_public
    incident.precision_level = normalize_precision_level(record.precision_level)
    incident.source_url = _clean(record.source_url)
    incident.verification_status = _clean(record.verification_status) or "reported"
    incident.data_last_seen_at = record.data_last_seen_at
    incident.is_public = bool(record.is_public)
    incident.is_aggregate = bool(record.is_aggregate)
    incident.notes = _clean(record.notes)

    # Apply auto-review — consolidates classify_record + resolve_publication_policy
    # + evidence/identifier confidence gates into one result.
    db_tier = resolve_publication_policy(
        db,
        source_key=source_key or record.source_name,
        source_name=record.source_name,
    )
    review = auto_review(
        record,
        record.source_name,
        has_snapshot_hash=import_batch_hash is not None,
        db_tier=db_tier,
    )
    if review.action == "block":
        raise CrimeIncidentValidationError("blocked_by_publish_rules")

    # Reset to auto-review decision if new, safety-changed, or previously rejected
    if incident.id is None or safety_fields_changed or prev_review_status == "rejected":
        incident.review_status = review.review_status
        incident.is_public = review.public_visibility
    else:
        incident.review_status = prev_review_status

    # Unconditional: quarantine/context_only action always revokes public visibility.
    if review.action in ("quarantine", "context_only"):
        incident.is_public = False
        if incident.review_status == "official_police_open_data_report":
            incident.review_status = "pending_review"

    db.flush()

    # Wire provenance and create ReviewItem for newly ingested records.
    if is_new:
        if source_snapshot_id is not None:
            incident.source_snapshot_id = source_snapshot_id
        review_item = ReviewItem(
            record_type="crime_incident",
            source_snapshot_id=source_snapshot_id,
            suggested_payload_json={
                "incident_type": incident.incident_type,
                "incident_category": incident.incident_category,
                "reported_at": (
                    incident.reported_at.isoformat() if incident.reported_at else None
                ),
                "city": incident.city,
                "province_state": incident.province_state,
                "country": incident.country,
                "public_area_label": incident.public_area_label,
                "precision_level": incident.precision_level,
                "source_name": incident.source_name,
                "external_id": incident.external_id,
            },
            source_url=incident.source_url,
            source_quality="official_police_open_data",
            confidence=review.confidence,
            privacy_status="generalized",
            publish_recommendation=review.review_status,
            public_visibility=False,
            status=PENDING,
        )
        db.add(review_item)
        db.flush()

    return incident


def derive_external_id(record: CrimeIncidentRecord) -> str:
    stable = "|".join(
        [
            record.source_name,
            record.incident_type,
            record.reported_at.isoformat() if record.reported_at else "",
            record.city or "",
            record.public_area_label or "",
        ]
    )
    return f"DERIVED-{hashlib.sha256(stable.encode('utf-8')).hexdigest()[:16].upper()}"


def normalize_incident_category(value: str) -> str:
    return "_".join(value.strip().lower().split())


def normalize_precision_level(value: str) -> str:
    return "_".join(value.strip().lower().split())


def _validate_record(record: CrimeIncidentRecord) -> None:
    if not record.source_name or not record.source_name.strip():
        raise CrimeIncidentValidationError("missing_source_name")
    if not record.incident_type or not record.incident_type.strip():
        raise CrimeIncidentValidationError("missing_incident_type")
    precision = normalize_precision_level(record.precision_level)
    if precision == "exact_address":
        raise CrimeIncidentValidationError("exact_address_precision_rejected")
    if precision not in GENERALIZED_PRECISION_LEVELS:
        raise CrimeIncidentValidationError(f"unsupported_precision_level:{precision}")
    if record.latitude_public is None or record.longitude_public is None:
        raise CrimeIncidentValidationError("missing_public_coordinates")
    if record.latitude_public == 0.0 or record.longitude_public == 0.0:
        raise CrimeIncidentValidationError("zero_public_coordinates")
    if record.notes and UNSAFE_NOTE_PATTERN.search(record.notes):
        raise CrimeIncidentValidationError("unsafe_private_or_person_specific_notes")
    if record.public_area_label and RESIDENCE_PATTERN.search(record.public_area_label):
        raise CrimeIncidentValidationError("unsafe_residence_in_public_area_label")
    if record.source_url and not record.source_url.strip().startswith(
        ("http://", "https://")
    ):
        raise CrimeIncidentValidationError("invalid_source_url")


def _clean(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
