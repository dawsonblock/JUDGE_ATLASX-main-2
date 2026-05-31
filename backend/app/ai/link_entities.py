from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.schemas import EntityLinkCandidate
from app.models.entities import Case, Court, Judge
from app.services.text import normalize_docket, normalize_name


def suggest_entity_links(db: Session, text: str, source_url: str | None, source_quality: str) -> list[EntityLinkCandidate]:
    candidates: list[EntityLinkCandidate] = []
    normalized = normalize_name(text)
    for judge in db.scalars(select(Judge)).all():
        if judge.normalized_name and judge.normalized_name in normalized:
            candidates.append(_candidate("judge", judge.id, judge.name, 0.84, source_url, source_quality))
    for court in db.scalars(select(Court)).all():
        if normalize_name(court.name) in normalized:
            candidates.append(_candidate("court", court.id, court.name, 0.82, source_url, source_quality))
    docket_normalized = normalize_docket(text)
    for case in db.scalars(select(Case)).all():
        if case.normalized_docket_number and case.normalized_docket_number in docket_normalized:
            candidates.append(_candidate("case", case.id, case.docket_number, 0.9, source_url, source_quality))
    return candidates


def _candidate(entity_type: str, entity_id: int, label: str, confidence: float, source_url: str | None, source_quality: str) -> EntityLinkCandidate:
    return EntityLinkCandidate(
        entity_type=entity_type,
        entity_id=entity_id,
        label=label,
        confidence=confidence,
        reason="Exact normalized text match in source.",
        source_url=source_url,
        source_quality=source_quality,
        source_quote="",
        neutral_summary=f"Potential {entity_type} link: {label}",
        privacy_risk=False,
        publish_recommendation="review_required",
    )

