"""Persist IngestionResult records to the database.

Called from the admin ``/run`` endpoint and Celery tasks after
``adapter.run()``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

from .adapters import (
    CreatedLegalInstrument,
    CreatedRecord,
    CreatedReviewItem,
    IngestionResult,
)
from .external_id import stable_record_identity
from .quarantine import quarantine_run
from .source_rules import check_record_type_allowed
from .statuses import PENDING, QUARANTINED
from ..policies.publication_policy import PENDING_REVIEW
from ..services.constants import AI_PUBLISH_RECOMMENDATIONS
from sqlalchemy.exc import IntegrityError
from ..models.entities import (
    CrimeIncident,
    IngestionRun,
    LegalInstrument,
    LegalSection,
    LegalSectionRevision,
    ReviewItem,
    SourceRegistry,
    SourceSnapshot,
)

Session = Any


_CREATED_RECORD_TYPE_MAP: dict[str, str] = {
    "crimeincident": "CrimeIncident",
    "crime_incident": "CrimeIncident",
    "event": "Event",
    "legalinstrument": "LegalInstrument",
    "legal_instrument": "LegalInstrument",
    "legalsection": "LegalSection",
    "legal_section": "LegalSection",
    "reviewitem": "ReviewItem",
    "review_item": "ReviewItem",
    "sourcesnapshot": "SourceSnapshot",
    "source_snapshot": "SourceSnapshot",
}


@dataclass
class RunPersistSummary:
    persisted_incidents: int = 0
    skipped_duplicates: int = 0
    persisted_review_items: int = 0
    persisted_legal_instruments: int = 0
    snapshots_written: int = 0
    quarantined_count: int = 0
    failed_records: int = 0
    review_items_skipped: int = 0
    contract_violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ── Machine-ingest contract ──────────────────────────────────────────────────

# Sources whose ``source_class`` is None are treated as legacy
# machine_ingest.
_MACHINE_INGEST_CLASSES: frozenset[str | None] = frozenset(
    ["machine_ingest", None]
)


def _validate_machine_ingest_contract(
    result: IngestionResult,
    source: SourceRegistry,
) -> list[str]:
    """Return contract-violation reason slugs for a machine_ingest run.

    An empty list means the result satisfies every requirement and may be
    persisted.  A non-empty list means the run must be quarantined.

    Requirements for machine_ingest sources:
    - ``result.raw_snapshot_bytes`` must be non-empty (real fetched content)
        - A source URL must be resolvable (``result.fetch_url`` or
            ``source.base_url``)
    - ``source.parser_version`` must be set (proves the adapter is versioned)
    """
    reasons: list[str] = []

    if source.is_active is False:
        reasons.append("source_disabled")

    if not result.raw_snapshot_bytes:
        reasons.append("no_raw_content")

    if not (result.fetch_url or source.base_url):
        reasons.append("no_fetch_url")

    if not source.parser_version:
        reasons.append("no_parser_version")
    elif result.parser_version is None:
        # source declares a required version but the adapter did not report one
        reasons.append("no_parser_version")
    elif result.parser_version != source.parser_version:
        reasons.append("parser_version_mismatch")

    # Adapters must never publish directly; they can only submit candidate
    # records for review. Any public/published marker in adapter payload is a
    # contract violation and run must be quarantined.
    for record in result.created_records:
        payload = getattr(record, "payload", {}) or {}
        if payload.get("is_public") is True:
            reasons.append("adapter_attempted_direct_publication")
            break
        visibility = payload.get("public_visibility")
        if isinstance(visibility, str) and visibility.strip().lower() == "public":
            reasons.append("adapter_attempted_direct_publication")
            break
        status = payload.get("review_status")
        if isinstance(status, str) and status.strip().lower() in {
            "approved",
            "verified_court_record",
            "official_police_open_data_report",
            "official_statistics_aggregate",
            "corrected",
        }:
            reasons.append("adapter_attempted_direct_publication")
            break

    return reasons


def _create_snapshot(
    db: Session,
    source: SourceRegistry,
    run_record: IngestionRun,
    raw_content: bytes | None = None,
    *,
    http_status: int | None = None,
    content_type: str | None = None,
    fetch_url: str | None = None,
) -> SourceSnapshot:
    """Create a SourceSnapshot for this run via the canonical snapshot writer.

    Routes through :func:`app.services.snapshot_writer.write_snapshot` so that
    all hash / integrity / evidence-store logic lives in one place.  When
    *raw_content* is ``None`` (the adapter did not produce raw bytes), an
    empty-bytes placeholder is written so snapshot integrity constraints are
    still satisfied.
    """
    from ..services.snapshot_writer import write_snapshot  # noqa: PLC0415

    content = raw_content if raw_content is not None else b""
    try:
        return write_snapshot(
            db=db,
            source_url=(
                fetch_url
                or source.base_url
                or f"internal://adapter/{source.source_key}"
            ),
            fetched_at=datetime.now(timezone.utc),
            content=content,
            http_status=http_status,
            content_type=content_type,
            ingestion_run_id=run_record.id,
            source_key=source.source_key,
        )
    except ValueError:
        run_record.status = QUARANTINED
        run_record.quarantine_reason = "no_raw_content"
        raise


def _insert_crime_incident(
    db: Session,
    record: CreatedRecord,
    snapshot: SourceSnapshot,
) -> bool:
    """Insert one CrimeIncident row.  Returns False on dedup (no insert)."""
    p = record.payload
    identity_hash = stable_record_identity(
        record.source_key,
        "crime_incident",
        p,
        record.external_id,
    )
    exists = (
        db.query(CrimeIncident.id)
        .filter(CrimeIncident.ingestion_identity_hash == identity_hash)
        .first()
    )
    if exists is not None:
        return False

    if record.external_id is not None:
        exists = (
            db.query(CrimeIncident.id)
            .filter(
                CrimeIncident.source_name == record.source_key,
                CrimeIncident.external_id == record.external_id,
            )
            .first()
        )
        if exists is not None:
            return False

    incident = CrimeIncident(
        source_id=record.source_key,
        external_id=record.external_id,
        incident_type=p.get("incident_type") or "unknown",
        incident_category=p.get("incident_category") or "other",
        reported_at=p.get("reported_at"),
        occurred_at=p.get("occurred_at"),
        city=p.get("city"),
        province_state=p.get("province_state"),
        country=p.get("country"),
        public_area_label=p.get("public_area_label"),
        latitude_public=p.get("latitude_public"),
        longitude_public=p.get("longitude_public"),
        precision_level=p.get("precision_level") or "general_area",
        source_url=record.source_url or p.get("source_url"),
        source_name=record.source_key,
        source_key=record.source_key,
        ingestion_identity_hash=identity_hash,
        verification_status=p.get("verification_status") or "reported",
        is_public=False,
        review_status="pending_review",
        source_snapshot_id=snapshot.id,
    )
    try:
        with db.begin_nested():
            db.add(incident)
            db.flush()
    except IntegrityError as exc:
        # Race-safe dedupe: if another worker inserted the same identity hash,
        # reuse the existing row path and continue ingestion.
        duplicate = (
            db.query(CrimeIncident.id)
            .filter(CrimeIncident.ingestion_identity_hash == identity_hash)
            .first()
        )
        if duplicate is not None:
            return False
        raise exc
    return True


def _summarize_warning_code(
    summary: RunPersistSummary,
    warning_code: str,
) -> None:
    if warning_code not in summary.warnings:
        summary.warnings.append(warning_code)


def _insert_review_item(
    db: Session,
    item: CreatedReviewItem,
    snapshot: SourceSnapshot,
    run_record: IngestionRun,
) -> bool:
    recommendation = (
        item.payload.get("publish_recommendation")
        or "review_required"
    )
    if recommendation not in AI_PUBLISH_RECOMMENDATIONS:
        recommendation = "review_required"

    identity = {
        "record_type": item.payload.get("record_type") or "unknown",
        "source_key": item.payload.get("source_key"),
        "unique_id": item.payload.get("unique_id"),
        "language": item.payload.get("language"),
        "instrument_type": item.payload.get("instrument_type"),
    }
    identity_hash = stable_record_identity(
        item.payload.get("source_key") or snapshot.source_key or "unknown",
        identity["record_type"],
        item.payload,
        item.payload.get("external_id"),
    )
    existing = (
        db.query(ReviewItem.id)
        .filter(ReviewItem.ingestion_identity_hash == identity_hash)
        .first()
    )
    if existing is not None:
        return False

    rv = ReviewItem(
        record_type=identity["record_type"],
        ingestion_identity_hash=identity_hash,
        source_snapshot_id=snapshot.id,
        suggested_payload_json=item.payload,
        source_url=item.url,
        source_quality=item.payload.get("source_quality") or "unverified",
        confidence=item.confidence_score,
        privacy_status=item.payload.get("privacy_status") or "unknown",
        publish_recommendation=recommendation,
        public_visibility=False,
        status=PENDING,
        ingestion_run_id=run_record.id,
    )
    try:
        with db.begin_nested():
            db.add(rv)
            db.flush()
    except IntegrityError as exc:
        duplicate = (
            db.query(ReviewItem.id)
            .filter(ReviewItem.ingestion_identity_hash == identity_hash)
            .first()
        )
        if duplicate is not None:
            return False
        raise exc
    return True


def _normalize_created_record_type(record_type: str | None) -> str:
    if not record_type:
        return ""
    normalized = record_type.strip()
    mapped = _CREATED_RECORD_TYPE_MAP.get(normalized.lower())
    return mapped or normalized


def _authority_types_for_result(result: IngestionResult) -> set[str]:
    required_types: set[str] = {"SourceSnapshot"}
    for record in result.created_records:
        normalized = _normalize_created_record_type(getattr(record, "record_type", None))
        if normalized:
            required_types.add(normalized)
    if result.legal_instruments:
        required_types.add("LegalInstrument")
        required_types.add("LegalSection")
    if result.review_items:
        required_types.add("ReviewItem")
    return required_types


def _parse_date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if not isinstance(value, str) or not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def _insert_or_update_legal_instrument(
    db: Session,
    source: SourceRegistry,
    instrument: CreatedLegalInstrument,
    snapshot: SourceSnapshot,
) -> None:
    p = instrument.payload
    row = (
        db.query(LegalInstrument)
        .filter(
            LegalInstrument.source_id == source.id,
            LegalInstrument.unique_id == instrument.unique_id,
            LegalInstrument.language == instrument.language,
        )
        .first()
    )
    if row is None:
        row = LegalInstrument(
            source_id=source.id,
            unique_id=instrument.unique_id,
            language=instrument.language,
            review_status=PENDING_REVIEW,
            public_visibility="private",
        )
        db.add(row)

    row.jurisdiction = p.get("jurisdiction") or "CA-FED"
    row.instrument_type = instrument.instrument_type
    row.title = instrument.title
    row.short_title = p.get("short_title")
    row.long_title = p.get("long_title")
    row.citation = p.get("citation")
    row.chapter_or_instrument_number = p.get("chapter_or_instrument_number")
    row.current_to_date = _parse_date(p.get("current_to_date"))
    row.last_amended_date = _parse_date(p.get("last_amended_date"))
    row.in_force_start_date = _parse_date(p.get("in_force_start_date"))
    row.consolidated_number = p.get("consolidated_number")
    row.link_to_xml = p.get("link_to_xml") or instrument.source_url
    row.link_to_html_toc = p.get("link_to_html_toc")
    row.raw_snapshot_id = snapshot.id
    row.parser_version = p.get("parser_version") or "1.0"
    if row.review_status not in {"verified_court_record", "corrected"}:
        row.review_status = PENDING_REVIEW
        row.public_visibility = "private"

    db.flush()

    for section in instrument.sections:
        label = section.get("section_label")
        text = section.get("text")
        if not label or not text:
            continue
        subsection = section.get("subsection_label")
        section_row = (
            db.query(LegalSection)
            .filter(
                LegalSection.legal_instrument_id == row.id,
                LegalSection.section_label == label,
                LegalSection.subsection_label == subsection,
            )
            .first()
        )
        if section_row is None:
            section_row = LegalSection(
                legal_instrument_id=row.id,
                section_label=label,
                subsection_label=subsection,
                text=text,
            )
            db.add(section_row)
            db.flush()
        previous_hash = section_row.content_hash
        new_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
        changed = previous_hash is not None and previous_hash != new_hash
        baseline_insert = previous_hash is None
        section_row.marginal_note = section.get("marginal_note")
        section_row.text = text
        section_row.section_key = section.get("section_key")
        section_row.content_hash = new_hash
        section_row.path = section.get("path")
        section_row.historical_note = section.get("historical_note")
        section_row.source_xml_node_id = section.get("source_xml_node_id")
        section_row.raw_snapshot_id = snapshot.id
        if section_row.text_version is None:
            section_row.text_version = 1
        if changed:
            section_row.text_version += 1
        if baseline_insert or changed:
            db.add(
                LegalSectionRevision(
                    legal_section_id=section_row.id,
                    revision_number=section_row.text_version,
                    previous_content_hash=previous_hash,
                    new_content_hash=new_hash,
                    diff_summary="section text changed",
                    raw_snapshot_id=snapshot.id,
                )
            )


def persist_ingestion_result(
    db: Session,
    source: SourceRegistry,
    run_record: IngestionRun,
    result: IngestionResult,
) -> RunPersistSummary:
    """Write IngestionResult records to the DB and return summary counts.

    Creates one SourceSnapshot per run, then inserts CrimeIncident rows for
    each CreatedRecord (deduped on source_key + external_id) and ReviewItem
    rows for each CreatedReviewItem.

    The caller is responsible for committing the session after this call.
    """
    summary = RunPersistSummary()

    # Defensive integrity check: adapter output must always belong to the
    # same source this run was invoked for.
    if result.source_key != source.source_key:
        quarantine_run(db, run_record, "source_key_mismatch")
        summary.contract_violations = ["source_key_mismatch"]
        summary.quarantined_count += 1
        return summary

    # ── Machine-ingest structural validation ─────────────────────────────────
    # For machine_ingest (and legacy None) sources, enforce the evidence
    # contract *before* writing anything.  Portal-reference and other classes
    # are not auto-ingested so they skip this gate.
    if source.source_class in _MACHINE_INGEST_CLASSES:
        contract_violations = _validate_machine_ingest_contract(result, source)
        if contract_violations:
            quarantine_run(
                db,
                run_record,
                "; ".join(contract_violations),
            )
            summary.contract_violations = contract_violations
            summary.quarantined_count += 1
            return summary

    # Enforce source authority before any persistence side effects.
    authority_types = _authority_types_for_result(result)
    authority_violations: list[str] = []
    for record_type in sorted(authority_types):
        violation = check_record_type_allowed(
            record_type,
            source.public_record_authority,
            source.creates,
        )
        if violation is not None:
            authority_violations.append(
                f"{record_type}:{violation.rule}:{violation.detail}"
            )
    if authority_violations:
        reason = "authority_violation: " + " | ".join(authority_violations)
        quarantine_run(db, run_record, reason)
        summary.contract_violations = authority_violations
        summary.quarantined_count += 1
        return summary

    # Always create a snapshot when raw bytes exist, even if no records were
    # parsed.
    # A zero-result run is still evidence: we fetched URL X at time Y with
    # HTTP status Z.
    # Skipping the snapshot loses audit information about what the adapter saw.
    has_records = bool(
        result.created_records
        or result.legal_instruments
        or result.review_items
    )
    has_raw_bytes = bool(result.raw_snapshot_bytes)

    if has_records and not has_raw_bytes:
        _summarize_warning_code(
            summary,
            "raw_snapshot_bytes absent — evidence provenance incomplete",
        )

    if not has_records and not has_raw_bytes:
        # Nothing to persist: no records and no raw evidence bytes.
        return summary

    try:
        snapshot = _create_snapshot(
            db,
            source,
            run_record,
            result.raw_snapshot_bytes,
            http_status=result.fetch_http_status,
            content_type=result.fetch_content_type,
            fetch_url=result.fetch_url,
        )
    except ValueError:
        # Snapshot writer already stamped run_record quarantine fields.
        summary.contract_violations = ["no_raw_content"]
        summary.quarantined_count += 1
        return summary
    summary.snapshots_written = 1

    if not has_records:
        # Snapshot-only run: raw bytes preserved, no parsed records.
        # This is valid evidence of a zero-result fetch.
        return summary

    for record in result.created_records:
        record_source_key = getattr(record, "source_key", source.source_key)
        if record_source_key != source.source_key:
            summary.failed_records += 1
            _summarize_warning_code(
                summary,
                "source_key_mismatch_record_rejected",
            )
            continue
        normalized_type = _normalize_created_record_type(record.record_type)
        if normalized_type != "CrimeIncident":
            summary.failed_records += 1
            _summarize_warning_code(
                summary,
                f"unsupported_created_record_type:{normalized_type or 'unknown'}",
            )
            continue
        try:
            if _insert_crime_incident(db, record, snapshot):
                summary.persisted_incidents += 1
            else:
                summary.skipped_duplicates += 1
                _summarize_warning_code(summary, "duplicate_record_skipped")
        except Exception:
            summary.failed_records += 1
            _summarize_warning_code(summary, "crime_incident_insert_failed")
            continue

    for instrument in result.legal_instruments:
        instrument_source_key = getattr(
            instrument,
            "source_key",
            source.source_key,
        )
        if instrument_source_key != source.source_key:
            summary.failed_records += 1
            _summarize_warning_code(
                summary,
                "source_key_mismatch_legal_rejected",
            )
            continue
        try:
            _insert_or_update_legal_instrument(
                db,
                source,
                instrument,
                snapshot,
            )
            summary.persisted_legal_instruments += 1
        except Exception:
            summary.failed_records += 1
            _summarize_warning_code(summary, "legal_instrument_insert_failed")
            continue

    for item in result.review_items:
        item_source_key = getattr(item, "source_key", source.source_key)
        if item_source_key != source.source_key:
            summary.review_items_skipped += 1
            _summarize_warning_code(
                summary,
                "source_key_mismatch_review_item_rejected",
            )
            continue
        try:
            if _insert_review_item(db, item, snapshot, run_record):
                summary.persisted_review_items += 1
            else:
                summary.review_items_skipped += 1
                _summarize_warning_code(
                    summary,
                    "duplicate_review_item_skipped",
                )
        except Exception:
            summary.review_items_skipped += 1
            _summarize_warning_code(summary, "review_item_insert_failed")
            continue

    # Reflect actual persist/skip counts back onto the run record before commit
    run_record.persisted_count = (
        summary.persisted_incidents
        + summary.persisted_legal_instruments
        + summary.persisted_review_items
    )
    run_record.skipped_count = (
        run_record.skipped_count or 0
    ) + summary.skipped_duplicates

    return summary
