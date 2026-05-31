"""Evidence chat service.

Given a natural-language question and an optional entity context
(incident_id or case_id), retrieves public RelationshipEvidence records
and constructs a deterministic, citation-backed answer.

No external LLM is invoked. Classification is rule-based, making
responses auditable and free from hallucination.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models.entities import (
    CrimeIncident,
    CrimeIncidentEventLink,
    Event,
    LegalInstrument,
    LegalSection,
    LegalSource,
    RelationshipEvidence,
    SourceSnapshot,
)
from app.policies.publication_policy import (
    PUBLIC_REVIEW_STATUSES,
    can_show_public_entity,
)
from app.services.text import normalize_text

_MAX_QUESTION_LEN: int = 500
_MAX_CITATIONS: int = 5
_DISCLAIMER: str = (
    "Evidence citations describe source records only. "
    "They are not proof of guilt, conviction, or any legal finding. "
    "All individuals are presumed innocent until proven guilty in a court of law."
)


@dataclass
class ChatCitation:
    evidence_id: int
    relationship_type: str
    evidence_type: str
    evidence_source: str
    excerpt: str | None
    confidence: float


@dataclass
class LegalContextCitation:
    legal_instrument_id: int
    legal_section_id: int
    title: str
    section_label: str
    language: str
    excerpt: str | None
    source_url: str | None


@dataclass
class ChatResponse:
    question: str
    answer: str
    citations: list[ChatCitation] = field(default_factory=list)
    legal_context_citations: list[LegalContextCitation] = field(default_factory=list)
    safety_notes: list[str] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)
    disclaimer: str = _DISCLAIMER
    incident_found: bool = False


def _legal_context_requested(question_tokens: set[str]) -> bool:
    legal_tokens = {
        "act",
        "code",
        "criminal",
        "law",
        "laws",
        "legal",
        "legislation",
        "regulation",
        "section",
        "statute",
    }
    return bool(question_tokens & legal_tokens)


def _legal_context_citations(
    db: Session,
    question_tokens: set[str],
) -> list[LegalContextCitation]:
    if not _legal_context_requested(question_tokens):
        return []

    rows = (
        db.query(LegalSection, LegalInstrument)
        .join(LegalInstrument, LegalInstrument.id == LegalSection.legal_instrument_id)
        .join(SourceSnapshot, SourceSnapshot.id == LegalInstrument.raw_snapshot_id)
        .filter(
            LegalInstrument.review_status.in_(PUBLIC_REVIEW_STATUSES),
            LegalInstrument.public_visibility == "public",
            LegalInstrument.raw_snapshot_id.is_not(None),
            SourceSnapshot.content_hash.is_not(None),
        )
        .limit(50)
        .all()
    )
    scored: list[tuple[float, LegalSection, LegalInstrument]] = []
    for section, instrument in rows:
        if not can_show_public_entity(db, "legal_instrument", instrument).allowed:
            continue
        text = " ".join(
            part
            for part in (
                instrument.title,
                instrument.short_title,
                instrument.long_title,
                section.section_label,
                section.marginal_note,
                section.text,
            )
            if part
        )
        tokens = set(normalize_text(text).split())
        overlap = len(question_tokens & tokens)
        if overlap == 0:
            continue
        scored.append((overlap / max(len(question_tokens), 1), section, instrument))

    scored.sort(key=lambda item: item[0], reverse=True)
    citations: list[LegalContextCitation] = []
    for _score, section, instrument in scored[:_MAX_CITATIONS]:
        excerpt = section.text[:200] + "\u2026" if len(section.text) > 200 else section.text
        citations.append(
            LegalContextCitation(
                legal_instrument_id=instrument.id,
                legal_section_id=section.id,
                title=instrument.title,
                section_label=section.section_label,
                language=instrument.language,
                excerpt=excerpt,
                source_url=instrument.link_to_xml,
            )
        )
    return citations


def _sanitize_question(question: str) -> str:
    """Strip ASCII control characters and enforce length cap."""
    cleaned = re.sub(r"[\x00-\x1f\x7f]", " ", question).strip()
    return cleaned[:_MAX_QUESTION_LEN]


def _score_evidence(evidence: RelationshipEvidence, question_tokens: set[str]) -> float:
    """Return a 0–1 relevance score based on keyword overlap and confidence."""
    text_parts = [
        part
        for part in (
            evidence.evidence_excerpt,
            evidence.relationship_type,
            evidence.evidence_type,
        )
        if part
    ]
    text = " ".join(text_parts)
    if not text:
        return evidence.confidence
    evidence_tokens = set(normalize_text(text).split())
    overlap = len(question_tokens & evidence_tokens)
    max_possible = max(len(question_tokens), 1)
    keyword_score = min(1.0, overlap / max_possible)
    return (keyword_score + evidence.confidence) / 2.0


def chat_about_evidence(
    db: Session,
    question: str,
    *,
    incident_id: int | None = None,
    case_id: int | None = None,
) -> ChatResponse:
    """Answer a question using stored public evidence records.

    Returns a :class:`ChatResponse` with citations from
    :class:`~app.models.entities.RelationshipEvidence` rows. Returns a
    "no evidence found" response when no matching records exist or when the
    requested incident is not public.

    Args:
        db: Active database session.
        question: Raw natural-language question from the caller.
        incident_id: Optional crime incident primary key. Evidence is only
            returned when ``CrimeIncident.is_public`` is ``True``.
        case_id: Optional court case primary key.
    """
    question = _sanitize_question(question)
    question_tokens = set(normalize_text(question).split())
    legal_context = _legal_context_citations(db, question_tokens)
    default_safety_note = "Answers are evidence-linked summaries and not legal findings."

    conditions = []
    incident_found = False

    if incident_id is not None:
        # Guard: only expose evidence for records the public can already see.
        incident = db.scalar(
            select(CrimeIncident).where(CrimeIncident.id == incident_id)
        )
        if incident is None or not can_show_public_entity(
            db, "crime_incident", incident
        ).allowed:
            # Incident does not exist or is not public — return nothing rather
            # than falling through to case_id queries and leaking related data.
            return ChatResponse(
                question=question,
                answer="No public evidence records found for the specified entity.",
                unsupported_claims=["No supporting evidence found for this question."],
                safety_notes=[default_safety_note],
                incident_found=False,
            )
        incident_found = True
        conditions.append(
            (RelationshipEvidence.from_entity_type == "crime_incident")
            & (RelationshipEvidence.from_entity_id == incident_id)
        )
        conditions.append(
            (RelationshipEvidence.to_entity_type == "crime_incident")
            & (RelationshipEvidence.to_entity_id == incident_id)
        )

    if case_id is not None:
        # Guard: only surface evidence when a public crime incident is linked to this case.
        linked_incidents = db.scalars(
            select(CrimeIncident)
            .join(
                CrimeIncidentEventLink,
                CrimeIncidentEventLink.crime_incident_id == CrimeIncident.id,
            )
            .join(Event, Event.id == CrimeIncidentEventLink.event_id)
            .where(
                Event.case_id == case_id,
            )
            .limit(50)
        ).all()
        if not any(
            can_show_public_entity(db, "crime_incident", linked).allowed
            for linked in linked_incidents
        ):
            return ChatResponse(
                question=question,
                answer="No public evidence records found for the specified entity.",
                incident_found=False,
            )
        conditions.append(
            (RelationshipEvidence.from_entity_type == "court_case")
            & (RelationshipEvidence.from_entity_id == case_id)
        )
        conditions.append(
            (RelationshipEvidence.to_entity_type == "court_case")
            & (RelationshipEvidence.to_entity_id == case_id)
        )

    if not conditions:
        if legal_context:
            parts = [
                f"Found {len(legal_context)} legal context citation(s) for your query.",
                "These citations describe legislation only, not incident facts.",
            ]
            return ChatResponse(
                question=question,
                answer=" ".join(parts),
                legal_context_citations=legal_context,
                safety_notes=[default_safety_note],
                incident_found=incident_found,
            )
        return ChatResponse(
            question=question,
            answer="No public evidence records found for the specified entity.",
            unsupported_claims=["No supporting evidence found for this question."],
            safety_notes=[default_safety_note],
            incident_found=incident_found,
        )

    stmt = select(RelationshipEvidence).where(
        or_(*conditions),
        RelationshipEvidence.confidence >= 0.25,
    )
    candidate_rows = list(db.scalars(stmt).all())
    evidence_rows: list[RelationshipEvidence] = []
    for evidence in candidate_rows:
        if not can_show_public_entity(db, "relationship_evidence", evidence).allowed:
            continue

        related_ok = True
        for side in ("from", "to"):
            entity_type = getattr(evidence, f"{side}_entity_type", None)
            entity_id = getattr(evidence, f"{side}_entity_id", None)
            if entity_type == "crime_incident" and entity_id is not None:
                incident = db.get(CrimeIncident, entity_id)
                if incident is None or not can_show_public_entity(
                    db, "crime_incident", incident
                ).allowed:
                    related_ok = False
                    break
            elif entity_type == "event" and entity_id is not None:
                event = db.get(Event, entity_id)
                if event is None or not can_show_public_entity(
                    db, "event", event
                ).allowed:
                    related_ok = False
                    break
            elif entity_type in {"source", "legal_source"} and entity_id is not None:
                source = db.get(LegalSource, entity_id)
                if source is None or not can_show_public_entity(
                    db, "legal_source", source
                ).allowed:
                    related_ok = False
                    break

        if related_ok:
            evidence_rows.append(evidence)

    if not evidence_rows:
        if legal_context:
            return ChatResponse(
                question=question,
                answer=(
                    f"Found {len(legal_context)} legal context citation(s), "
                    "but no relationship evidence records are available for this entity."
                ),
                legal_context_citations=legal_context,
                unsupported_claims=["No incident-specific supporting evidence found for this question."],
                safety_notes=[default_safety_note],
                incident_found=incident_found,
            )
        return ChatResponse(
            question=question,
            answer="No relationship evidence records are available for this entity.",
            unsupported_claims=["No supporting evidence found for this question."],
            safety_notes=[default_safety_note],
            incident_found=incident_found,
        )

    # Rank by relevance to the question.
    scored = sorted(
        evidence_rows,
        key=lambda e: _score_evidence(e, question_tokens),
        reverse=True,
    )
    top = scored[:_MAX_CITATIONS]

    citations = [
        ChatCitation(
            evidence_id=e.id,
            relationship_type=e.relationship_type,
            evidence_type=e.evidence_type,
            evidence_source=e.evidence_source,
            excerpt=e.evidence_excerpt,
            confidence=e.confidence,
        )
        for e in top
    ]

    # Construct a plain-language answer from the top evidence.
    parts: list[str] = [
        f"Found {len(citations)} evidence record(s) for your query.",
        "Most relevant:",
    ]
    for i, c in enumerate(citations, 1):
        raw_excerpt = c.excerpt or "(no excerpt)"
        snippet = (
            raw_excerpt[:200] + "\u2026" if len(raw_excerpt) > 200 else raw_excerpt
        )
        parts.append(f"{i}. [{c.relationship_type} / {c.evidence_type}] {snippet}")

    return ChatResponse(
        question=question,
        answer=" ".join(parts),
        citations=citations,
        legal_context_citations=legal_context,
        safety_notes=[default_safety_note],
        incident_found=incident_found,
    )
