from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class LocationOut(BaseModel):
    id: int
    name: str
    city: str | None
    state: str | None
    region: str | None
    latitude: float
    longitude: float

    model_config = ConfigDict(from_attributes=True)


class CourtOut(BaseModel):
    id: int
    courtlistener_id: str
    name: str
    jurisdiction: str | None
    region: str | None
    location: LocationOut

    model_config = ConfigDict(from_attributes=True)


class JudgeOut(BaseModel):
    id: int
    name: str
    court_id: int | None

    model_config = ConfigDict(from_attributes=True)


class JudgeSummaryOut(BaseModel):
    id: int
    name: str
    court_id: int | None
    cl_person_id: str | None
    public_event_count: int

    model_config = ConfigDict(from_attributes=True)


class DefendantOut(BaseModel):
    id: int
    anonymized_id: str
    display_label: str

    model_config = ConfigDict(from_attributes=True)


class SourceOut(BaseModel):
    id: int
    source_id: str
    source_type: str
    title: str
    url: str
    source_quality: str
    verified_flag: bool
    review_status: str

    model_config = ConfigDict(from_attributes=True)


class OutcomeOut(BaseModel):
    id: int
    outcome_type: str
    outcome_date: date | None
    summary: str

    model_config = ConfigDict(from_attributes=True)


class EventOut(BaseModel):
    event_id: str
    court_id: int
    judge_id: int | None
    case_id: int
    primary_location_id: int
    event_type: str
    event_subtype: str | None
    decision_result: str | None
    decision_date: date | None
    posted_date: date | None
    title: str
    summary: str
    repeat_offender_indicator: bool
    repeat_offender_indicators: list[str] = Field(default_factory=list)
    verification_status: str | None = None
    source_excerpt: str | None = None
    is_mappable: bool
    location_status: str
    verified_flag: bool
    source_quality: str
    last_verified_at: datetime | None
    review_status: str
    court: CourtOut | None = None
    judge: JudgeOut | None = None
    defendants: list[DefendantOut] = Field(default_factory=list)
    sources: list[SourceOut] = Field(default_factory=list)
    outcomes: list[OutcomeOut] = Field(default_factory=list)
    outcome_status: str | None = None

    model_config = ConfigDict(from_attributes=True)


class EventCreate(BaseModel):
    court_id: int
    judge_id: int | None = None
    case_id: int
    primary_location_id: int
    event_type: str
    event_subtype: str | None = None
    decision_result: str | None = None
    decision_date: date | None = None
    posted_date: date | None = None
    title: str
    summary: str
    repeat_offender_indicator: bool = False
    verified_flag: bool = False
    source_quality: str = "court_record"


class CaseOut(BaseModel):
    id: int
    court_id: int
    docket_number: str
    caption: str
    case_type: str
    filed_date: date | None
    terminated_date: date | None

    model_config = ConfigDict(from_attributes=True)


class GeoJsonFeatureCollection(BaseModel):
    type: str
    features: list[dict[str, Any]]


class MapRecordOut(BaseModel):
    """Normalized public map record schema.

    This schema standardizes the API response for all record types displayed
    on the public map: court events, crime incidents, news context, etc.
    """

    # Core identification
    id: int
    record_type: str  # court_event | crime_incident | news_context | law_policy | judge_profile

    # Content
    title: str
    summary: str | None = None
    event_date: date | None = None

    # Location (generalized coordinates only)
    latitude: float
    longitude: float
    location_label: str | None = None
    location_precision: str  # city_centroid, neighbourhood, courthouse, etc.
    city: str | None = None
    region: str | None = None  # province/state
    country: str | None = None

    # Source provenance
    source_tier: str  # court_record, official_police_open_data, etc.
    source_urls: list[str] = Field(default_factory=list)

    # Review status
    review_status: str  # verified_court_record, pending_review, etc.
    confidence: float = 0.0  # 0.0 to 1.0
    warnings: list[str] = Field(default_factory=list)

    # Optional court/legal fields (may be null for non-court records)
    court_name: str | None = None
    case_name: str | None = None
    docket_number: str | None = None
    judge_name: str | None = None
    charge_category: str | None = None
    outcome: str | None = None

    # Related records
    related_records: list[dict[str, Any]] = Field(default_factory=list)

    # Metadata
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)
