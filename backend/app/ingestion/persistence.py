import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.adapters import ParsedRecord
from app.models.entities import Case, Court, Event, EventDefendant, EventSource, Judge, LegalSource, Location
from app.services.classifier import classify_event
from app.services.constants import ALLOWED_EVENT_TYPES
from app.services.linker import link_defendant_by_case, url_hash
from app.services.publish_rules import classify_record, public_visibility_for_tier, review_status_for_tier
from app.services.text import normalize_docket, normalize_name

VERIFIED_SOURCE_QUALITIES = {
    "court_record",
    "court_order",
    "appeal_decision",
    "official_statement",
}


@dataclass(frozen=True)
class PersistResult:
    persisted: bool
    skipped: bool
    case_id: int | None = None
    event_id: str | None = None
    source_id: int | None = None
    reason: str | None = None


def is_verified_source_quality(source_quality: str) -> bool:
    return source_quality in VERIFIED_SOURCE_QUALITIES


def persist_parsed_record(db: Session, parsed: ParsedRecord) -> PersistResult:
    if not parsed.docket_number:
        return PersistResult(persisted=False, skipped=True, reason="missing_docket_number")

    court = _get_or_create_court(db, parsed)
    judge = _get_or_create_judge(db, parsed.judge_name, court)
    case = _get_or_create_case(db, parsed, court)
    source = _get_or_create_source(db, parsed)

    classification = classify_event(parsed.docket_text or "")
    if classification.event_type not in ALLOWED_EVENT_TYPES or not classification.matched_keywords:
        db.flush()
        return PersistResult(persisted=False, skipped=True, case_id=case.id, source_id=source.id, reason="no_supported_event")

    deterministic_id = _event_id(parsed, classification.event_type)
    event = db.scalar(select(Event).where(Event.event_id == deterministic_id))
    if not event:
        is_verified = is_verified_source_quality(parsed.source_quality)
        event = Event(
            event_id=deterministic_id,
            court_id=court.id,
            judge_id=judge.id if judge else None,
            case_id=case.id,
            primary_location_id=court.location_id,
            event_type=classification.event_type,
            event_subtype="courtlistener_docket",
            decision_result=classification.event_type,
            decision_date=parsed.entry_date or parsed.date_filed,
            posted_date=parsed.entry_date,
            title=_event_title(parsed, classification.event_type),
            summary=_safe_summary(parsed.docket_text),
            repeat_offender_indicator=classification.repeat_offender_indicator,
            verified_flag=is_verified,
            source_quality=parsed.source_quality,
            last_verified_at=datetime.now(timezone.utc) if is_verified else None,
            classifier_metadata={
                "confidence": classification.confidence,
                "matched_keywords": classification.matched_keywords,
                "repeat_offender_indicators": classification.repeat_offender_indicators,
                "verification_status": "indicator_only" if classification.repeat_offender_indicator else "not_indicated",
                "source_excerpt": _source_excerpt(parsed.docket_text, classification.matched_keywords),
            },
            review_status=review_status_for_tier(classify_record(parsed.source_name, parsed)),
            public_visibility=public_visibility_for_tier(classify_record(parsed.source_name, parsed)),
        )
        db.add(event)
        db.flush()

    _link_event_source(db, event, source)
    _link_reliable_defendants(db, case, event, parsed.parties)
    db.flush()
    return PersistResult(persisted=True, skipped=False, case_id=case.id, event_id=event.event_id, source_id=source.id)


def _get_or_create_court(db: Session, parsed: ParsedRecord) -> Court:
    code = parsed.court_code or "unknown"
    court = db.scalar(select(Court).where(Court.courtlistener_id == code))
    if court:
        return court

    location = db.scalar(select(Location).where(Location.name == f"CourtListener placeholder: {code}"))
    if not location:
        location = Location(
            name=f"CourtListener placeholder: {code}",
            location_type="court_placeholder",
            city=None,
            state=None,
            region=None,
            latitude=0.0,
            longitude=0.0,
        )
        db.add(location)
        db.flush()

    court = Court(
        courtlistener_id=code,
        name=parsed.court_name or f"CourtListener court {code}",
        jurisdiction="Federal",
        region=None,
        location_id=location.id,
    )
    db.add(court)
    db.flush()
    return court


def _get_or_create_judge(db: Session, judge_name: str | None, court: Court) -> Judge | None:
    normalized = normalize_name(judge_name)
    if not normalized:
        return None
    judge = db.scalar(select(Judge).where(Judge.normalized_name == normalized))
    if judge:
        return judge
    judge = Judge(name=judge_name or normalized, normalized_name=normalized, court_id=court.id)
    db.add(judge)
    db.flush()
    return judge


def _get_or_create_case(db: Session, parsed: ParsedRecord, court: Court) -> Case:
    normalized_docket = normalize_docket(parsed.docket_number)
    case = db.scalar(select(Case).where(Case.court_id == court.id, Case.normalized_docket_number == normalized_docket))
    if case:
        return case
    case = Case(
        court_id=court.id,
        docket_number=parsed.docket_number or normalized_docket,
        normalized_docket_number=normalized_docket,
        caption=parsed.caption or "Unknown caption",
        case_type="criminal",
        filed_date=parsed.date_filed,
        terminated_date=parsed.date_terminated,
        courtlistener_docket_id=parsed.docket_id,
    )
    db.add(case)
    db.flush()
    return case


def _get_or_create_source(db: Session, parsed: ParsedRecord) -> LegalSource:
    url = parsed.source_public_url or parsed.source_url or parsed.source_api_url or "https://www.courtlistener.com/"
    hashed = url_hash(url)
    source = db.scalar(select(LegalSource).where(LegalSource.url_hash == hashed))
    if source:
        if parsed.source_api_url and not source.api_url:
            source.api_url = parsed.source_api_url
        return source
    source_id = f"SRC-CL-{hashlib.sha256(url.encode('utf-8')).hexdigest()[:12].upper()}"
    source = LegalSource(
        source_id=source_id,
        source_type=parsed.source_quality,
        title=parsed.caption or parsed.docket_number or "CourtListener source",
        url=url,
        api_url=parsed.source_api_url,
        url_hash=hashed,
        source_quality=parsed.source_quality,
        verified_flag=is_verified_source_quality(parsed.source_quality),
        retrieved_at=datetime.now(timezone.utc),
        review_status="pending_review",
        public_visibility=False,
    )
    db.add(source)
    db.flush()
    return source


def _link_event_source(db: Session, event: Event, source: LegalSource) -> None:
    existing = db.scalar(select(EventSource).where(EventSource.event_id == event.id, EventSource.source_id == source.id))
    if not existing:
        db.add(EventSource(event_id=event.id, source_id=source.id))


def _link_reliable_defendants(db: Session, case: Case, event: Event, parties: list[dict]) -> None:
    for party in parties:
        party_type = normalize_name(str(party.get("party_type") or party.get("type") or party.get("role") or ""))
        name = party.get("name") or party.get("party_name") or party.get("public_name")
        if "defendant" not in party_type or not name:
            continue
        defendant = link_defendant_by_case(db, case, str(name))
        existing = db.scalar(select(EventDefendant).where(EventDefendant.event_id == event.id, EventDefendant.defendant_id == defendant.id))
        if not existing:
            db.add(EventDefendant(event_id=event.id, defendant_id=defendant.id))


def _event_id(parsed: ParsedRecord, event_type: str) -> str:
    """Build stable event ID from docket + entry + document identifiers.

    Documented fallback: when entry IDs are missing, uses docket + entry_date.
    """
    entry_id = parsed.docket_entry_id or str(parsed.entry_number or "")
    doc_id = parsed.recap_document_id or ""
    date_fallback = parsed.entry_date.isoformat() if (not entry_id and parsed.entry_date) else ""
    stable_parts = [
        parsed.court_code or "unknown",
        normalize_docket(parsed.docket_number),
        entry_id,
        doc_id,
        date_fallback,
        event_type,
    ]
    stable = "|".join(stable_parts)
    return f"EVT-CL-{hashlib.sha256(stable.encode('utf-8')).hexdigest()[:16].upper()}"


def _event_title(parsed: ParsedRecord, event_type: str) -> str:
    label = event_type.replace("_", " ")
    docket = parsed.docket_number or "unknown docket"
    return f"CourtListener {label} for {docket}"


def _safe_summary(text: str | None) -> str:
    if not text:
        return "CourtListener docket event classified from docket metadata."
    compact = " ".join(text.split())
    return compact[:1000]


def _source_excerpt(text: str | None, keywords: list[str]) -> str | None:
    if not text or not keywords:
        return None
    lower = text.lower()
    first_index = min((lower.find(keyword) for keyword in keywords if lower.find(keyword) >= 0), default=0)
    start = max(0, first_index - 120)
    end = min(len(text), first_index + 240)
    return " ".join(text[start:end].split())
