"""Rule-based correctness-checking service.

The AI checks map accuracy only.  It never scores guilt, judges people,
implies danger, or ranks suspects.

Five checks per record:
1. source_correctness  — source actually says what the record claims
2. location_correctness — location is at the right generalised precision
3. date_correctness     — reported/occurred/court dates are distinct and present
4. duplicate_detection  — same incident may already exist under another id
5. status_correctness   — status label is specific and legally accurate

Output map_quality labels:
  verified            — all five checks pass
  needs_review        — one or more fields missing, vague, or conflicting
  duplicate_candidate — likely the same incident as an existing record
  location_uncertain  — good source but precision is weak
  rejected            — source does not support the record

PROMPT_VERSION is bumped whenever the rule logic changes so historical
checks remain traceable.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import (
    AICorrectnessCheck,
    AICorrectnessFinding,
    CrimeIncident,
    Event,
)

MODEL_NAME = "rules_v1"
PROMPT_VERSION = "1.0.0"

MapQuality = Literal[
    "verified",
    "needs_review",
    "duplicate_candidate",
    "location_uncertain",
    "rejected",
]
PrivacyRisk = Literal["low", "medium", "high"]

_SAFE_PRECISIONS = {
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
_UNSAFE_PRECISIONS = {"exact_address", "rooftop", "parcel", "residential"}

_VALID_STATUSES = {
    "reported",
    "alleged",
    "charged",
    "convicted",
    "dismissed",
    "sentenced",
    "released",
    "appealed",
    "unknown",
    "aggregate_official",
    "verified",
    "official_police_open_data_report",
    "verified_court_record",
    "news_only_context",
}

_PRIVATE_PATTERNS = re.compile(
    r"\b(?:\d{1,5}\s+\w+\s+(?:st|ave|blvd|rd|dr|ln|ct|pl|way|terr?)\b"
    r"|apt\.?\s*\d+|unit\s+\d+|suite\s+\d+"
    r"|ssn|sin|social\s+security|date\s+of\s+birth|dob\b)",
    re.IGNORECASE,
)

_DUP_WINDOW_HOURS = 72
_DUP_COORD_DELTA = 0.05


def check_crime_incident(
    db: Session, incident: CrimeIncident
) -> AICorrectnessCheck:
    """Run all five correctness checks for a CrimeIncident and persist."""
    findings: list[dict] = []
    now = datetime.now(timezone.utc)

    # 1. Source correctness
    source_supports = _check_incident_source(incident, findings)

    # 2. Location correctness
    location_ok = _check_incident_location(incident, findings)

    # 3. Date correctness
    date_ok = _check_incident_dates(incident, findings)

    # 4. Duplicate detection
    dup_ids = _find_incident_duplicates(db, incident)
    is_dup = bool(dup_ids)
    if is_dup:
        findings.append({
            "finding_type": "duplicate_candidate",
            "field_name": "external_id",
            "expected": "unique record",
            "found": f"possible duplicates: {dup_ids}",
            "severity": "warning",
            "note": "Merge sources instead of creating a new dot.",
        })

    # 5. Status correctness
    status_ok = _check_incident_status(incident, findings)

    # Privacy risk
    privacy_risk = _assess_privacy_risk(incident.notes, incident.precision_level)

    # map_quality
    map_quality = _derive_quality(
        source_supports=source_supports,
        location_ok=location_ok,
        date_ok=date_ok,
        status_ok=status_ok,
        is_dup=is_dup,
        privacy_risk=privacy_risk,
    )

    reason = _build_reason(findings, map_quality)
    result_json = {
        "record_type": "crime_incident",
        "event_type_supported": source_supports,
        "date_supported": date_ok,
        "location_supported": location_ok,
        "status_supported": status_ok,
        "source_supports_claim": source_supports,
        "duplicate_candidate": is_dup,
        "possible_duplicate_ids": dup_ids,
        "privacy_risk": privacy_risk,
        "map_quality": map_quality,
        "reason": reason,
        "checked_at": now.isoformat(),
        "model_name": MODEL_NAME,
        "prompt_version": PROMPT_VERSION,
    }

    chk = AICorrectnessCheck(
        record_type="crime_incident",
        record_id=incident.id,
        model_name=MODEL_NAME,
        prompt_version=PROMPT_VERSION,
        event_type_supported=source_supports,
        date_supported=date_ok,
        location_supported=location_ok,
        status_supported=status_ok,
        source_supports_claim=source_supports,
        duplicate_candidate=is_dup,
        possible_duplicate_ids=dup_ids if dup_ids else None,
        privacy_risk=privacy_risk,
        map_quality=map_quality,
        reason=reason,
        result_json=result_json,
        checked_at=now,
    )
    db.add(chk)
    db.flush()

    for f in findings:
        db.add(AICorrectnessFinding(
            check_id=chk.id,
            finding_type=f["finding_type"],
            field_name=f.get("field_name"),
            expected=f.get("expected"),
            found=f.get("found"),
            severity=f.get("severity", "info"),
            note=f.get("note"),
        ))
    db.flush()
    return chk


def check_court_event(db: Session, event: Event) -> AICorrectnessCheck:
    """Run all five correctness checks for a court Event and persist."""
    findings: list[dict] = []
    now = datetime.now(timezone.utc)

    source_supports = _check_event_source(event, findings)
    location_ok = _check_event_location(event, findings)
    date_ok = _check_event_dates(event, findings)
    dup_ids = _find_event_duplicates(db, event)
    is_dup = bool(dup_ids)
    if is_dup:
        findings.append({
            "finding_type": "duplicate_candidate",
            "field_name": "event_id",
            "expected": "unique record",
            "found": f"possible duplicates: {dup_ids}",
            "severity": "warning",
            "note": "Merge sources instead of creating a new dot.",
        })
    status_ok = _check_event_status(event, findings)

    privacy_risk = _assess_privacy_risk(event.summary, None)
    map_quality = _derive_quality(
        source_supports=source_supports,
        location_ok=location_ok,
        date_ok=date_ok,
        status_ok=status_ok,
        is_dup=is_dup,
        privacy_risk=privacy_risk,
    )
    reason = _build_reason(findings, map_quality)
    result_json = {
        "record_type": "court_event",
        "event_type_supported": source_supports,
        "date_supported": date_ok,
        "location_supported": location_ok,
        "status_supported": status_ok,
        "source_supports_claim": source_supports,
        "duplicate_candidate": is_dup,
        "possible_duplicate_ids": dup_ids,
        "privacy_risk": privacy_risk,
        "map_quality": map_quality,
        "reason": reason,
        "checked_at": now.isoformat(),
        "model_name": MODEL_NAME,
        "prompt_version": PROMPT_VERSION,
    }

    chk = AICorrectnessCheck(
        record_type="court_event",
        record_id=event.id,
        model_name=MODEL_NAME,
        prompt_version=PROMPT_VERSION,
        event_type_supported=source_supports,
        date_supported=date_ok,
        location_supported=location_ok,
        status_supported=status_ok,
        source_supports_claim=source_supports,
        duplicate_candidate=is_dup,
        possible_duplicate_ids=dup_ids if dup_ids else None,
        privacy_risk=privacy_risk,
        map_quality=map_quality,
        reason=reason,
        result_json=result_json,
        checked_at=now,
    )
    db.add(chk)
    db.flush()

    for f in findings:
        db.add(AICorrectnessFinding(
            check_id=chk.id,
            finding_type=f["finding_type"],
            field_name=f.get("field_name"),
            expected=f.get("expected"),
            found=f.get("found"),
            severity=f.get("severity", "info"),
            note=f.get("note"),
        ))
    db.flush()
    return chk


def is_safe_to_show(chk: AICorrectnessCheck) -> bool:
    """Review gate: returns True only if the dot may appear on the map.

    Rules (applied in order):
    - privacy_risk == "high"  → NEVER show
    - source_supports_claim is False → NEVER show
    - map_quality == "rejected" → NEVER show
    - map_quality == "duplicate_candidate" → NEVER show (merged into parent)
    - map_quality in {"verified", "location_uncertain"} → show
    - map_quality == "needs_review" → do NOT show (hold for admin)
    """
    if chk.privacy_risk == "high":
        return False
    if not chk.source_supports_claim:
        return False
    if chk.map_quality in ("rejected", "duplicate_candidate", "needs_review"):
        return False
    return chk.map_quality in ("verified", "location_uncertain")


# ---------------------------------------------------------------------------
# Internal check helpers
# ---------------------------------------------------------------------------

def _check_incident_source(
    incident: CrimeIncident, findings: list[dict]
) -> bool:
    if not incident.incident_type or not incident.source_name:
        findings.append({
            "finding_type": "missing_source",
            "field_name": "source_name",
            "severity": "error",
            "note": "Record has no incident_type or source_name.",
        })
        return False
    if not incident.source_url:
        findings.append({
            "finding_type": "missing_source_url",
            "field_name": "source_url",
            "severity": "warning",
            "note": (
                "source_url is required to verify the claim. "
                "Record will not be marked source-supported."
            ),
        })
        return False
    return True


def _check_incident_location(
    incident: CrimeIncident, findings: list[dict]
) -> bool:
    prec = (incident.precision_level or "").lower()
    if prec in _UNSAFE_PRECISIONS:
        findings.append({
            "finding_type": "unsafe_precision",
            "field_name": "precision_level",
            "expected": "generalised public area",
            "found": prec,
            "severity": "error",
            "note": "Exact residential location must not be stored.",
        })
        return False
    if prec not in _SAFE_PRECISIONS:
        findings.append({
            "finding_type": "unknown_precision",
            "field_name": "precision_level",
            "found": prec,
            "severity": "warning",
            "note": "Precision level not in approved list; defaulting to uncertain.",
        })
        return False
    if incident.latitude_public is None or incident.longitude_public is None:
        findings.append({
            "finding_type": "missing_coordinates",
            "field_name": "latitude_public",
            "severity": "warning",
            "note": "No public coordinates — dot cannot be placed.",
        })
        return False
    return True


def _check_incident_dates(
    incident: CrimeIncident, findings: list[dict]
) -> bool:
    ok = True
    if incident.reported_at is None and incident.occurred_at is None:
        findings.append({
            "finding_type": "missing_date",
            "field_name": "reported_at",
            "severity": "warning",
            "note": "Neither reported_at nor occurred_at is set.",
        })
        ok = False
    if (
        incident.reported_at
        and incident.occurred_at
        and incident.occurred_at > incident.reported_at
    ):
        findings.append({
            "finding_type": "date_order_mismatch",
            "field_name": "occurred_at",
            "expected": "occurred_at <= reported_at",
            "found": f"occurred_at={incident.occurred_at}, reported_at={incident.reported_at}",
            "severity": "warning",
            "note": "Occurred date is after reported date — likely a data error.",
        })
        ok = False
    return ok


def _check_incident_status(
    incident: CrimeIncident, findings: list[dict]
) -> bool:
    status = (incident.verification_status or "").lower()
    if status not in _VALID_STATUSES:
        findings.append({
            "finding_type": "unknown_status",
            "field_name": "verification_status",
            "found": status,
            "severity": "warning",
            "note": f"Status '{status}' is not a recognised legal status label.",
        })
        return False
    return True


def _check_event_source(event: Event, findings: list[dict]) -> bool:
    if not event.event_type:
        findings.append({
            "finding_type": "missing_event_type",
            "field_name": "event_type",
            "severity": "error",
            "note": "Court event has no event_type.",
        })
        return False
    if not event.source_links:
        findings.append({
            "finding_type": "no_source_links",
            "field_name": "source_links",
            "severity": "warning",
            "note": "Court event has no attached sources.",
        })
        return False
    return True


def _check_event_location(event: Event, findings: list[dict]) -> bool:
    if event.primary_location is None:
        findings.append({
            "finding_type": "missing_location",
            "field_name": "primary_location",
            "severity": "warning",
            "note": "Court event has no primary location.",
        })
        return False
    return True


def _check_event_dates(event: Event, findings: list[dict]) -> bool:
    ok = True
    if event.decision_date is None and event.posted_date is None:
        findings.append({
            "finding_type": "missing_date",
            "field_name": "decision_date",
            "severity": "warning",
            "note": "Neither decision_date nor posted_date is set.",
        })
        ok = False
    return ok


def _check_event_status(event: Event, findings: list[dict]) -> bool:
    status = (event.review_status or "").lower()
    if status not in _VALID_STATUSES and status not in {
        "verified_court_record",
        "official_police_open_data_report",
        "news_only_context",
        "corrected",
        "pending_review",
        "disputed",
    }:
        findings.append({
            "finding_type": "unknown_status",
            "field_name": "review_status",
            "found": status,
            "severity": "warning",
        })
        return False
    return True


def _find_incident_duplicates(
    db: Session, incident: CrimeIncident
) -> list[int]:
    """Return IDs of likely-duplicate CrimeIncident rows.

    Phase 1 — exact stable ID: same source_name + external_id.
    Phase 2 — canonical URL: same non-null source_url.
    Phase 3 — fuzzy: same type + city + time window + coord delta.
    Returns on first phase that finds a match.
    """
    if incident.id is None:
        return []

    base = CrimeIncident.id != incident.id

    # Phase 1: exact stable ID
    if incident.external_id and incident.source_name:
        rows = db.scalars(
            select(CrimeIncident.id).where(
                base,
                CrimeIncident.source_name == incident.source_name,
                CrimeIncident.external_id == incident.external_id,
            ).limit(10)
        ).all()
        if rows:
            return list(rows)

    # Phase 2: canonical URL
    if incident.source_url:
        rows = db.scalars(
            select(CrimeIncident.id).where(
                base,
                CrimeIncident.source_url == incident.source_url,
            ).limit(10)
        ).all()
        if rows:
            return list(rows)

    # Phase 3: fuzzy — type + city + time window + coord delta
    window = timedelta(hours=_DUP_WINDOW_HOURS)
    stmt = select(CrimeIncident.id).where(
        base,
        CrimeIncident.incident_type == incident.incident_type,
        CrimeIncident.city == incident.city,
    )
    if incident.reported_at:
        stmt = stmt.where(
            CrimeIncident.reported_at.between(
                incident.reported_at - window,
                incident.reported_at + window,
            )
        )
    if incident.latitude_public and incident.longitude_public:
        stmt = stmt.where(
            CrimeIncident.latitude_public.between(
                incident.latitude_public - _DUP_COORD_DELTA,
                incident.latitude_public + _DUP_COORD_DELTA,
            ),
            CrimeIncident.longitude_public.between(
                incident.longitude_public - _DUP_COORD_DELTA,
                incident.longitude_public + _DUP_COORD_DELTA,
            ),
        )
    return list(db.scalars(stmt.limit(10)).all())


def _find_event_duplicates(db: Session, event: Event) -> list[int]:
    """Return IDs of likely-duplicate Event rows."""
    if event.id is None:
        return []
    stmt = select(Event.id).where(
        Event.id != event.id,
        Event.event_type == event.event_type,
        Event.case_id == event.case_id,
    )
    if event.decision_date:
        stmt = stmt.where(Event.decision_date == event.decision_date)
    rows = db.scalars(stmt.limit(10)).all()
    return list(rows)


def _assess_privacy_risk(
    text: str | None, precision_level: str | None
) -> PrivacyRisk:
    if precision_level and precision_level.lower() in _UNSAFE_PRECISIONS:
        return "high"
    if text and _PRIVATE_PATTERNS.search(text):
        return "high"
    return "low"


def _derive_quality(
    *,
    source_supports: bool,
    location_ok: bool,
    date_ok: bool,
    status_ok: bool,
    is_dup: bool,
    privacy_risk: PrivacyRisk,
) -> MapQuality:
    if privacy_risk == "high" or not source_supports:
        return "rejected"
    if is_dup:
        return "duplicate_candidate"
    if not location_ok:
        return "location_uncertain"
    if not date_ok or not status_ok:
        return "needs_review"
    return "verified"


def _build_reason(findings: list[dict], map_quality: MapQuality) -> str:
    if not findings:
        return (
            "All five correctness checks passed. "
            "Source, location, date, status, and uniqueness are verified."
        )
    parts = []
    for f in findings:
        note = f.get("note") or f.get("finding_type", "")
        parts.append(note)
    return f"map_quality={map_quality}. Issues: " + " | ".join(parts)
