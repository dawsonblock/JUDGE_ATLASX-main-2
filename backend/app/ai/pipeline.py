from typing import Any

from sqlalchemy.orm import Session

from app.ai.classify import classify_crime_record, classify_legal_record
from app.ai.link_entities import suggest_entity_links
from app.ai.redaction import redact_private_data
from app.ai.schemas import AISourceAnalysis, ExtractedCrimeIncident, ExtractedLegalEvent
from app.ai.summarize import neutral_crime_summary, neutral_legal_summary
from app.ingestion.statuses import PENDING
from app.models.entities import ReviewItem


def analyze_source(db: Session, raw_source: dict[str, Any]) -> AISourceAnalysis:
    text = str(raw_source.get("text") or raw_source.get("content") or raw_source.get("summary") or "")
    source_url = raw_source.get("source_url") or raw_source.get("url")
    source_quality = str(raw_source.get("source_quality") or "unknown")
    record_type = str(raw_source.get("record_type") or _infer_record_type(source_quality, text))
    redaction = redact_private_data(text, source_url, source_quality)
    source_quote = redaction.source_quote
    recommendation = "block" if redaction.publish_recommendation == "block" else "review_required"

    if record_type == "crime_incident":
        crime_classification = classify_crime_record(redaction.redacted_text)
        payload = ExtractedCrimeIncident(
            source_url=source_url,
            source_quality=source_quality,
            confidence=min(redaction.confidence, crime_classification.confidence),
            source_quote=source_quote,
            neutral_summary=neutral_crime_summary(redaction.redacted_text, source_quote),
            privacy_risk=redaction.privacy_risk,
            publish_recommendation=recommendation,
            incident_type=str(raw_source.get("incident_type") or crime_classification.incident_category),
            incident_category=crime_classification.incident_category,
            reported_at=raw_source.get("reported_at"),
            city=raw_source.get("city"),
            public_area_label=raw_source.get("public_area_label"),
        )
    else:
        legal_classification = classify_legal_record(redaction.redacted_text)
        payload = ExtractedLegalEvent(
            source_url=source_url,
            source_quality=source_quality,
            confidence=min(redaction.confidence, legal_classification.confidence),
            source_quote=source_quote,
            neutral_summary=neutral_legal_summary(redaction.redacted_text, source_quote),
            privacy_risk=redaction.privacy_risk,
            publish_recommendation=recommendation,
            event_type=legal_classification.event_type,
            title=str(raw_source.get("title") or "AI drafted legal event"),
            summary=neutral_legal_summary(redaction.redacted_text, source_quote),
            decision_date=raw_source.get("decision_date"),
            court_id=raw_source.get("court_id"),
            judge_id=raw_source.get("judge_id"),
            case_id=raw_source.get("case_id"),
            primary_location_id=raw_source.get("primary_location_id"),
            repeat_offender_indicator=legal_classification.repeat_offender_indicator,
            repeat_offender_indicators=legal_classification.repeat_offender_indicators,
        )

    if not payload.privacy_risk and _is_low_risk_official_source(source_quality, payload.model_dump()):
        payload.publish_recommendation = "safe_auto_publish"

    links = suggest_entity_links(db, redaction.redacted_text, source_url, source_quality)
    return AISourceAnalysis(
        source_url=source_url,
        source_quality=source_quality,
        confidence=payload.confidence,
        source_quote=source_quote,
        neutral_summary=payload.neutral_summary,
        privacy_risk=payload.privacy_risk,
        publish_recommendation=payload.publish_recommendation,
        record_type=payload.record_type,
        extracted_payload=payload.model_dump(),
        link_candidates=links,
    )


def create_review_item(db: Session, analysis: AISourceAnalysis, raw_source_id: int | None = None) -> ReviewItem:
    item = ReviewItem(
        record_type=analysis.record_type,
        raw_source_id=raw_source_id,
        suggested_payload_json={
            **analysis.extracted_payload,
            "link_candidates": [candidate.model_dump() for candidate in analysis.link_candidates],
        },
        source_url=analysis.source_url,
        source_quality=analysis.source_quality,
        confidence=analysis.confidence,
        privacy_status="privacy_risk" if analysis.privacy_risk else "no_private_data_detected",
        publish_recommendation=analysis.publish_recommendation,
        status="blocked" if analysis.publish_recommendation == "block" else PENDING,
    )
    db.add(item)
    db.flush()
    return item


def run_ai_pipeline(db: Session, raw_source: dict[str, Any], raw_source_id: int | None = None) -> ReviewItem:
    analysis = analyze_source(db, raw_source)
    return create_review_item(db, analysis, raw_source_id)


def _infer_record_type(source_quality: str, text: str) -> str:
    normalized = f"{source_quality} {text}".lower()
    if "police" in normalized or "reported incident" in normalized or "crime" in normalized:
        return "crime_incident"
    return "legal_event"


def _is_low_risk_official_source(source_quality: str, payload: dict[str, Any]) -> bool:
    official = source_quality in {"court_record", "court_order", "official_statement", "official_police_open_data"}
    if not official:
        return False
    if payload.get("repeat_offender_indicator"):
        return False
    return True
