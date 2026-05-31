from typing import Any, Literal

from pydantic import BaseModel, Field

PublishRecommendation = Literal["safe_auto_publish", "review_required", "block"]


class AIBaseOutput(BaseModel):
    source_url: str | None
    source_quality: str
    confidence: float = Field(ge=0.0, le=1.0)
    source_quote: str
    neutral_summary: str
    privacy_risk: bool
    publish_recommendation: PublishRecommendation


class RedactionResult(AIBaseOutput):
    redacted_text: str
    detected_risks: list[str] = Field(default_factory=list)


class ExtractedLegalEvent(AIBaseOutput):
    record_type: Literal["legal_event"] = "legal_event"
    event_type: str
    title: str
    summary: str
    decision_date: str | None = None
    court_id: int | None = None
    judge_id: int | None = None
    case_id: int | None = None
    primary_location_id: int | None = None
    repeat_offender_indicator: bool = False
    repeat_offender_indicators: list[str] = Field(default_factory=list)


class ExtractedCrimeIncident(AIBaseOutput):
    record_type: Literal["crime_incident"] = "crime_incident"
    incident_type: str
    incident_category: str
    reported_at: str | None = None
    city: str | None = None
    public_area_label: str | None = None


class EntityLinkCandidate(BaseModel):
    entity_type: str
    entity_id: str | int | None = None
    label: str
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    source_url: str | None = None
    source_quality: str = "unknown"
    source_quote: str = ""
    neutral_summary: str = ""
    privacy_risk: bool = False
    publish_recommendation: PublishRecommendation = "review_required"


class AISourceAnalysis(AIBaseOutput):
    record_type: Literal["legal_event", "crime_incident", "unknown"]
    extracted_payload: dict[str, Any]
    link_candidates: list[EntityLinkCandidate] = Field(default_factory=list)


class AIReviewDecision(AIBaseOutput):
    record_type: str
    suggested_payload: dict[str, Any]
    review_reason: str

