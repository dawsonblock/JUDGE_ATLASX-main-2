"""AI evidence chat API endpoint.

POST /api/chat/evidence

Returns evidence-backed answers to questions about tracked incidents and cases.
Responses are citation-grounded and include a mandatory legal disclaimer.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.orm import Session

from app.core.rate_limit import rate_limit_public
from app.db.session import get_db
from app.services.evidence_chat import (
    _MAX_QUESTION_LEN,
    chat_about_evidence,
)

router = APIRouter(prefix="/api/chat", tags=["chat"])


class EvidenceChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(..., min_length=3, max_length=_MAX_QUESTION_LEN)
    incident_id: int | None = Field(None, ge=1)
    case_id: int | None = Field(None, ge=1)

    @field_validator("question")
    @classmethod
    def question_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("question must not be blank")
        return v


class CitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    evidence_id: int
    relationship_type: str
    evidence_type: str
    evidence_source: str
    excerpt: str | None
    confidence: float


class LegalContextCitationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    legal_instrument_id: int
    legal_section_id: int
    title: str
    section_label: str
    language: str
    excerpt: str | None
    source_url: str | None


class EvidenceChatResponse(BaseModel):
    question: str
    answer: str
    citations: list[CitationOut]
    legal_context_citations: list[LegalContextCitationOut] = []
    disclaimer: str
    incident_found: bool
    safety_notes: list[str] = []
    unsupported_claims: list[str] = []


@router.post(
    "/evidence",
    response_model=EvidenceChatResponse,
    dependencies=[Depends(rate_limit_public)],
)
def post_evidence_chat(
    body: EvidenceChatRequest,
    db: Session = Depends(get_db),
) -> EvidenceChatResponse:
    """Answer a question about stored relationship evidence.

    When ``incident_id`` or ``case_id`` is supplied, relationship evidence is
    scoped to that public entity. Legal-context questions may omit both IDs and
    return approved legislation citations only.
    """
    result = chat_about_evidence(
        db,
        body.question,
        incident_id=body.incident_id,
        case_id=body.case_id,
    )
    return EvidenceChatResponse(
        question=result.question,
        answer=result.answer,
        citations=[
            CitationOut(
                evidence_id=c.evidence_id,
                relationship_type=c.relationship_type,
                evidence_type=c.evidence_type,
                evidence_source=c.evidence_source,
                excerpt=c.excerpt,
                confidence=c.confidence,
            )
            for c in result.citations
        ],
        legal_context_citations=[
            LegalContextCitationOut(
                legal_instrument_id=c.legal_instrument_id,
                legal_section_id=c.legal_section_id,
                title=c.title,
                section_label=c.section_label,
                language=c.language,
                excerpt=c.excerpt,
                source_url=c.source_url,
            )
            for c in result.legal_context_citations
        ],
        disclaimer=result.disclaimer,
        incident_found=result.incident_found,
        safety_notes=result.safety_notes,
        unsupported_claims=result.unsupported_claims,
    )
