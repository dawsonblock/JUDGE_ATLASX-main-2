import hashlib
import json
from datetime import date, datetime, timezone
from uuid import uuid4

from app.db.session import Base
from app.ingestion.statuses import PENDING, QUARANTINED, RUNNING
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    case,
    func,
)
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Mapped, mapped_column, relationship


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Location(Base, TimestampMixin):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    location_type: Mapped[str] = mapped_column(
        String(80), nullable=False, default="courthouse"
    )
    city: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(80))
    region: Mapped[str | None] = mapped_column(String(80))
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    geocode_cache_id: Mapped[int | None] = mapped_column(ForeignKey("geocode_cache.id"), nullable=True)
    # NOTE: geom column exists only on PostgreSQL (PostGIS), managed by Alembic.
    # The ORM does not map it because bbox filtering uses lat/lon only.
    # Future: Add geom mapping when triggers/generated columns maintain it.


class Court(Base, TimestampMixin):
    __tablename__ = "courts"

    def __init__(self, **kwargs):
        """Back-compat initializer for legacy test fixtures."""
        # Discard parameters that don't exist in current schema
        kwargs.pop("court_level", None)  # Legacy field, no longer used

        if not kwargs.get("courtlistener_id"):
            kwargs["courtlistener_id"] = uuid4().hex[:32]

        if kwargs.get("location_id") is None and "location" not in kwargs:
            # Legacy fixtures often construct Court before persisting Location.
            kwargs["location"] = Location(
                name=f"Court Placeholder {uuid4().hex[:8]}",
                location_type="court_placeholder",
                latitude=0.0,
                longitude=0.0,
            )

        super().__init__(**kwargs)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    courtlistener_id: Mapped[str] = mapped_column(
        String(32), nullable=False, unique=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    jurisdiction: Mapped[str | None] = mapped_column(String(80))
    region: Mapped[str | None] = mapped_column(String(80))
    location_id: Mapped[int] = mapped_column(ForeignKey("locations.id"), nullable=False)

    location: Mapped[Location] = relationship()
    cases: Mapped[list["Case"]] = relationship(back_populates="court")
    events: Mapped[list["Event"]] = relationship(back_populates="court")
    cl_provenance: Mapped[dict | None] = mapped_column(JSON)


class Judge(Base, TimestampMixin):
    __tablename__ = "judges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    normalized_name: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    court_id: Mapped[int | None] = mapped_column(ForeignKey("courts.id"))
    cl_person_id: Mapped[str | None] = mapped_column(
        String(80), unique=True, index=True
    )

    court: Mapped[Court | None] = relationship()
    events: Mapped[list["Event"]] = relationship(back_populates="judge")


class Case(Base, TimestampMixin):
    __tablename__ = "cases"
    __table_args__ = (
        UniqueConstraint(
            "court_id",
            "normalized_docket_number",
            name="uq_case_court_normalized_docket",
        ),
    )

    def __init__(self, **kwargs):
        """Back-compat initializer for legacy case fixtures."""
        case_number = kwargs.pop("case_number", None)
        kwargs.pop("jurisdiction", None)  # Legacy field

        if case_number and not kwargs.get("docket_number"):
            kwargs["docket_number"] = case_number

        if not kwargs.get("normalized_docket_number"):
            docket = kwargs.get("docket_number") or case_number
            if docket:
                kwargs["normalized_docket_number"] = (
                    str(docket)
                    .strip()
                    .lower()
                    .replace(" ", "-")
                    .replace(":", "-")
                    .replace("/", "-")
                )

        if not kwargs.get("caption"):
            label = kwargs.get("docket_number") or kwargs.get("normalized_docket_number") or "unknown"
            kwargs["caption"] = f"Case {label}"

        super().__init__(**kwargs)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    court_id: Mapped[int] = mapped_column(ForeignKey("courts.id"), nullable=False)
    docket_number: Mapped[str] = mapped_column(String(120), nullable=False)
    normalized_docket_number: Mapped[str] = mapped_column(String(120), nullable=False)
    caption: Mapped[str] = mapped_column(String(500), nullable=False)
    case_type: Mapped[str] = mapped_column(String(80), default="criminal")
    filed_date: Mapped[date | None] = mapped_column(Date)
    terminated_date: Mapped[date | None] = mapped_column(Date)
    courtlistener_docket_id: Mapped[str | None] = mapped_column(String(80), index=True)

    court: Mapped[Court] = relationship(back_populates="cases")
    parties: Mapped[list["CaseParty"]] = relationship(back_populates="case")
    events: Mapped[list["Event"]] = relationship(back_populates="case")
    court_events: Mapped[list["CourtEvent"]] = relationship(
        back_populates="case", order_by="CourtEvent.event_date"
    )
    cl_provenance: Mapped[dict | None] = mapped_column(JSON)


class Defendant(Base, TimestampMixin):
    __tablename__ = "defendants"

    def __init__(self, **kwargs):
        """Back-compat initializer for legacy defendant fixtures."""
        legacy_name = kwargs.pop("name", None)
        kwargs.pop("jurisdiction", None)  # Legacy field

        if legacy_name and not kwargs.get("public_name"):
            kwargs["public_name"] = legacy_name

        if not kwargs.get("normalized_public_name") and kwargs.get("public_name"):
            kwargs["normalized_public_name"] = kwargs["public_name"].strip().lower()

        if not kwargs.get("anonymized_id"):
            kwargs["anonymized_id"] = uuid4().hex[:24]

        super().__init__(**kwargs)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    anonymized_id: Mapped[str] = mapped_column(
        String(24), nullable=False, unique=True, index=True
    )
    public_name: Mapped[str | None] = mapped_column(String(255))
    normalized_public_name: Mapped[str | None] = mapped_column(String(255), index=True)

    parties: Mapped[list["CaseParty"]] = relationship(back_populates="defendant")
    event_links: Mapped[list["EventDefendant"]] = relationship(
        back_populates="defendant"
    )


class CaseParty(Base, TimestampMixin):
    __tablename__ = "case_parties"
    __table_args__ = (
        UniqueConstraint(
            "case_id", "normalized_name", "party_type", name="uq_case_party_name_type"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False)
    defendant_id: Mapped[int | None] = mapped_column(ForeignKey("defendants.id"))
    party_type: Mapped[str] = mapped_column(String(80), nullable=False)
    public_name: Mapped[str | None] = mapped_column(String(255))
    normalized_name: Mapped[str | None] = mapped_column(String(255), index=True)

    case: Mapped[Case] = relationship(back_populates="parties")
    defendant: Mapped[Defendant | None] = relationship(back_populates="parties")


class Event(Base, TimestampMixin):
    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    court_id: Mapped[int] = mapped_column(ForeignKey("courts.id"), nullable=False)
    judge_id: Mapped[int | None] = mapped_column(ForeignKey("judges.id"))
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id"), nullable=False)
    primary_location_id: Mapped[int] = mapped_column(
        ForeignKey("locations.id"), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    event_subtype: Mapped[str | None] = mapped_column(String(120))
    decision_result: Mapped[str | None] = mapped_column(String(120))
    decision_date: Mapped[date | None] = mapped_column(Date, index=True)
    posted_date: Mapped[date | None] = mapped_column(Date)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    repeat_offender_indicator: Mapped[bool] = mapped_column(
        "repeat_offender_flag", Boolean, default=False, nullable=False
    )
    verified_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_quality: Mapped[str] = mapped_column(String(80), default="court_record")
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    classifier_metadata: Mapped[dict | None] = mapped_column(JSON)
    review_status: Mapped[str] = mapped_column(
        String(80), default="pending_review", nullable=False, index=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[str | None] = mapped_column(String(120))
    review_notes: Mapped[str | None] = mapped_column(Text)
    correction_note: Mapped[str | None] = mapped_column(Text)
    dispute_note: Mapped[str | None] = mapped_column(Text)
    public_visibility: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )

    court: Mapped[Court] = relationship(back_populates="events")
    judge: Mapped[Judge | None] = relationship(back_populates="events")
    case: Mapped[Case] = relationship(back_populates="events")
    primary_location: Mapped[Location] = relationship()
    defendant_links: Mapped[list["EventDefendant"]] = relationship(
        back_populates="event"
    )
    source_links: Mapped[list["EventSource"]] = relationship(back_populates="event")
    outcomes: Mapped[list["Outcome"]] = relationship(back_populates="event")
    cl_provenance: Mapped[dict | None] = mapped_column(JSON)

    def __init__(self, **kwargs):
        """Back-compat initializer for legacy test fixtures."""
        # Discard parameters that don't exist in current schema
        kwargs.pop("incident_type", None)  # Legacy field
        kwargs.pop("event_date", None)    # Use decision_date instead
        super().__init__(**kwargs)

class EventDefendant(Base):
    __tablename__ = "event_defendants"
    __table_args__ = (
        UniqueConstraint("event_id", "defendant_id", name="uq_event_defendant"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    defendant_id: Mapped[int] = mapped_column(
        ForeignKey("defendants.id"), nullable=False
    )

    event: Mapped[Event] = relationship(back_populates="defendant_links")
    defendant: Mapped[Defendant] = relationship(back_populates="event_links")


class LegalSource(Base, TimestampMixin):
    __tablename__ = "legal_sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True
    )
    source_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    api_url: Mapped[str | None] = mapped_column(Text)
    url_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    source_quality: Mapped[str] = mapped_column(String(80), nullable=False)
    verified_flag: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    retrieved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    review_status: Mapped[str] = mapped_column(
        String(80), default="pending_review", nullable=False, index=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[str | None] = mapped_column(String(120))
    review_notes: Mapped[str | None] = mapped_column(Text)
    correction_note: Mapped[str | None] = mapped_column(Text)
    dispute_note: Mapped[str | None] = mapped_column(Text)
    public_visibility: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    cl_provenance: Mapped[dict | None] = mapped_column(JSON)

    event_links: Mapped[list["EventSource"]] = relationship(back_populates="source")

    def __init__(self, **kwargs):
        """Back-compat initializer for legacy test fixtures."""
        # Map legacy parameter names to current schema
        source_key = kwargs.pop("source_key", None)
        if source_key is not None and "source_id" not in kwargs:
            kwargs["source_id"] = source_key

        lifecycle_state = kwargs.pop("lifecycle_state", None)

        # Persist deprecated/quarantined/blocked lifecycle states via review_status
        # so legacy gate checks continue to work with the current schema.
        if lifecycle_state in {"deprecated", QUARANTINED, "blocked"}:
            kwargs.setdefault("review_status", lifecycle_state)

        kwargs.pop("is_active", None)
        # Set defaults for required fields if not provided
        kwargs.setdefault("title", "Test Legal Source")

        source_id = kwargs.get("source_id")
        if "url" not in kwargs:
            if source_id:
                kwargs["url"] = f"manual://{source_id}"
            else:
                kwargs["url"] = f"manual://autogen-{uuid4().hex}"

        url_value = str(kwargs.get("url") or "").strip()
        if not url_value:
            raise ValueError("url_hash requires a non-empty URL")

        kwargs.setdefault(
            "url_hash",
            hashlib.sha256(url_value.encode("utf-8")).hexdigest(),
        )
        kwargs.setdefault("source_type", "manual_reference")
        kwargs.setdefault("source_quality", "unknown")

        kwargs.pop("source_name", None)  # Legacy field, use source_id instead
        super().__init__(**kwargs)

    @property
    def lifecycle_state(self) -> str | None:
        """Back-compat lifecycle state view derived from review_status."""
        if self.review_status in {"deprecated", QUARANTINED, "blocked"}:
            return self.review_status
        return None

    @lifecycle_state.setter
    def lifecycle_state(self, value: str | None) -> None:
        if value in {"deprecated", QUARANTINED, "blocked"}:
            self.review_status = value

class CrimeIncident(Base, TimestampMixin):
    __tablename__ = "crime_incidents"
    __table_args__ = (
        UniqueConstraint(
            "source_name", "external_id", name="uq_crime_incident_source_external"
        ),
        UniqueConstraint(
            "source_key", "external_id", name="uq_crime_incident_sourcekey_external"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[str | None] = mapped_column(String(120), index=True)
    external_id: Mapped[str | None] = mapped_column(String(120), index=True)
    incident_type: Mapped[str] = mapped_column(String(120), nullable=False)
    incident_category: Mapped[str] = mapped_column(
        String(80), nullable=False, index=True
    )
    reported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    occurred_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    city: Mapped[str | None] = mapped_column(String(120), index=True)
    province_state: Mapped[str | None] = mapped_column(String(120), index=True)
    country: Mapped[str | None] = mapped_column(String(80), index=True)
    public_area_label: Mapped[str | None] = mapped_column(String(255))
    latitude_public: Mapped[float | None] = mapped_column(Float)
    longitude_public: Mapped[float | None] = mapped_column(Float)
    precision_level: Mapped[str] = mapped_column(
        String(80), default="general_area", nullable=False
    )
    source_url: Mapped[str | None] = mapped_column(Text)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_key: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )  # FK-like reference to SourceRegistry.source_key (populated on ingest)
    ingestion_identity_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    verification_status: Mapped[str] = mapped_column(
        String(80), default="reported", nullable=False, index=True
    )
    data_last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_public: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    notes: Mapped[str | None] = mapped_column(Text)
    review_status: Mapped[str] = mapped_column(
        String(80), default="pending_review", nullable=False, index=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reviewed_by: Mapped[str | None] = mapped_column(String(120))
    review_notes: Mapped[str | None] = mapped_column(Text)
    correction_note: Mapped[str | None] = mapped_column(Text)
    dispute_note: Mapped[str | None] = mapped_column(Text)

    is_aggregate: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )

    # Timeline fields for case progression tracking
    cleared_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )  # When the case was cleared/resolved
    disposition: Mapped[str | None] = mapped_column(
        String(50), index=True
    )  # "open", "arrested", "charged", "convicted", "acquitted", "dismissed", "withdrawn"
    linked_case_ids: Mapped[list[int] | None] = mapped_column(
        JSON
    )  # References to related Court cases (Case.id values)

    # Provenance: SourceSnapshot that produced this record (set on first ingest)
    source_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_snapshots.id"), nullable=True, index=True
    )
    source_snapshot: Mapped["SourceSnapshot"] = relationship(
        "SourceSnapshot", foreign_keys=[source_snapshot_id]
    )

    source_links: Mapped[list["CrimeIncidentSource"]] = relationship(
        back_populates="incident"
    )
    event_links: Mapped[list["CrimeIncidentEventLink"]] = relationship(
        back_populates="incident"
    )


class CrimeAggregateStatistic(Base, TimestampMixin):
    __tablename__ = "crime_aggregate_statistics"
    __table_args__ = (
        UniqueConstraint(
            "source_key",
            "aggregate_key",
            name="uq_crime_aggregate_source_key",
        ),
        Index("ix_crime_aggregate_period", "period"),
        Index("ix_crime_aggregate_geography", "geography"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    aggregate_key: Mapped[str] = mapped_column(String(255), nullable=False)
    period: Mapped[str | None] = mapped_column(String(64), index=True)
    geography: Mapped[str | None] = mapped_column(String(255), index=True)
    statistic_name: Mapped[str | None] = mapped_column(String(255))
    unit: Mapped[str | None] = mapped_column(String(120))
    value_numeric: Mapped[float | None] = mapped_column(Float)
    metadata_json: Mapped[dict | None] = mapped_column(JSON)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_snapshots.id"), nullable=True, index=True
    )

    source_snapshot: Mapped["SourceSnapshot"] = relationship(
        "SourceSnapshot", foreign_keys=[source_snapshot_id]
    )


class EvidenceReview(Base):
    __tablename__ = "evidence_reviews"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    previous_status: Mapped[str | None] = mapped_column(String(80))
    new_status: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(120))
    reviewed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    notes: Mapped[str | None] = mapped_column(Text)
    public_visibility: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )


class ReviewItem(Base):
    __tablename__ = "review_items"

    def __init__(self, **kwargs):
        """Back-compat initializer for legacy review item fixtures."""
        item_type = kwargs.pop("item_type", None)
        if item_type is not None and "record_type" not in kwargs:
            kwargs["record_type"] = item_type

        kwargs.setdefault("record_type", "generic")
        kwargs.setdefault("suggested_payload_json", {})
        kwargs.setdefault("source_quality", "unknown")
        kwargs.setdefault("privacy_status", "needs_review")
        kwargs.setdefault("publish_recommendation", "hold")

        super().__init__(**kwargs)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    raw_source_id: Mapped[int | None] = mapped_column(Integer, index=True)
    source_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_snapshots.id"), nullable=True, index=True
    )
    suggested_payload_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    source_quality: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    privacy_status: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    publish_recommendation: Mapped[str] = mapped_column(
        String(80), nullable=False, index=True
    )
    public_visibility: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    ingestion_identity_hash: Mapped[str | None] = mapped_column(
        String(64), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(80), default=PENDING, nullable=False, index=True
    )
    reviewer_id: Mapped[str | None] = mapped_column(String(120))
    reviewer_notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Link to ingestion run that created this review item
    ingestion_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("ingestion_runs.id"), nullable=True, index=True
    )
    ingestion_run: Mapped["IngestionRun"] = relationship()

    action_logs: Mapped[list["ReviewActionLog"]] = relationship(
        back_populates="review_item"
    )
    source_snapshot: Mapped["SourceSnapshot"] = relationship()


class ReviewActionLog(Base):
    __tablename__ = "review_action_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    review_item_id: Mapped[int] = mapped_column(
        ForeignKey("review_items.id"), nullable=False, index=True
    )
    actor: Mapped[str] = mapped_column(String(120), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    before_json: Mapped[dict | None] = mapped_column(JSON)
    after_json: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    review_item: Mapped[ReviewItem] = relationship(back_populates="action_logs")


class LegalInstrument(Base, TimestampMixin):
    """Federal/provincial legal instrument ingested as legal context."""

    __tablename__ = "legal_instruments"
    __table_args__ = (
        UniqueConstraint(
            "source_id",
            "unique_id",
            "language",
            name="uq_legal_instruments_source_unique_language",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("source_registry.id", name="fk_legal_instruments_source_id"),
        nullable=False,
        index=True,
    )
    jurisdiction: Mapped[str] = mapped_column(String(50), nullable=False)
    instrument_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    unique_id: Mapped[str] = mapped_column(String(100), nullable=False)
    language: Mapped[str] = mapped_column(String(5), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    short_title: Mapped[str | None] = mapped_column(Text)
    long_title: Mapped[str | None] = mapped_column(Text)
    citation: Mapped[str | None] = mapped_column(String(255))
    chapter_or_instrument_number: Mapped[str | None] = mapped_column(String(100))
    current_to_date: Mapped[date | None] = mapped_column(Date)
    last_amended_date: Mapped[date | None] = mapped_column(Date)
    in_force_start_date: Mapped[date | None] = mapped_column(Date)
    consolidated_number: Mapped[str | None] = mapped_column(String(100))
    link_to_xml: Mapped[str | None] = mapped_column(Text)
    link_to_html_toc: Mapped[str | None] = mapped_column(Text)
    raw_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_snapshots.id"), nullable=True, index=True
    )
    parser_version: Mapped[str] = mapped_column(
        String(50), nullable=False, default="1.0", server_default="1.0"
    )
    review_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending_review",
        server_default="pending_review",
        index=True,
    )
    public_visibility: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="private",
        server_default="private",
        index=True,
    )

    source: Mapped["SourceRegistry"] = relationship()
    raw_snapshot: Mapped["SourceSnapshot"] = relationship()
    sections: Mapped[list["LegalSection"]] = relationship(
        "LegalSection",
        back_populates="legal_instrument",
        cascade="all, delete-orphan",
    )


class LegalSection(Base, TimestampMixin):
    """A section or subsection of an ingested legal instrument."""

    __tablename__ = "legal_sections"
    __table_args__ = (
        UniqueConstraint(
            "legal_instrument_id",
            "section_label",
            "subsection_label",
            name="uq_legal_sections_instrument_label",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    legal_instrument_id: Mapped[int] = mapped_column(
        ForeignKey(
            "legal_instruments.id",
            ondelete="CASCADE",
            name="fk_legal_sections_legal_instrument_id",
        ),
        nullable=False,
        index=True,
    )
    section_label: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    subsection_label: Mapped[str | None] = mapped_column(String(50))
    section_key: Mapped[str | None] = mapped_column(String(80), index=True)
    marginal_note: Mapped[str | None] = mapped_column(Text)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    text_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    path: Mapped[str | None] = mapped_column(String(255))
    historical_note: Mapped[str | None] = mapped_column(Text)
    source_xml_node_id: Mapped[str | None] = mapped_column(String(100))
    raw_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_snapshots.id"), nullable=True, index=True
    )
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="1"
    )
    superseded_by_section_key: Mapped[str | None] = mapped_column(
        String(80), nullable=True
    )

    legal_instrument: Mapped[LegalInstrument] = relationship(back_populates="sections")
    raw_snapshot: Mapped["SourceSnapshot"] = relationship()


class LegalSectionRevision(Base, TimestampMixin):
    """Versioned revision history for legal section text changes."""

    __tablename__ = "legal_section_revisions"
    __table_args__ = (
        UniqueConstraint(
            "legal_section_id",
            "revision_number",
            name="uq_legal_section_revisions_section_revision",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    legal_section_id: Mapped[int] = mapped_column(
        ForeignKey("legal_sections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_content_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    new_content_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True
    )
    diff_summary: Mapped[str | None] = mapped_column(Text)
    raw_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_snapshots.id"), nullable=True, index=True
    )
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    change_type: Mapped[str | None] = mapped_column(String(40), nullable=True)

    legal_section: Mapped[LegalSection] = relationship()
    raw_snapshot: Mapped["SourceSnapshot"] = relationship()


class EventSource(Base):
    __tablename__ = "event_sources"
    __table_args__ = (
        UniqueConstraint("event_id", "source_id", name="uq_event_source"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    source_id: Mapped[int] = mapped_column(
        ForeignKey("legal_sources.id"), nullable=False
    )
    supports_outcome: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )

    event: Mapped[Event] = relationship(back_populates="source_links")
    source: Mapped[LegalSource] = relationship(back_populates="event_links")


class Outcome(Base, TimestampMixin):
    __tablename__ = "outcomes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("events.id"), nullable=False)
    outcome_type: Mapped[str] = mapped_column(String(120), nullable=False)
    outcome_date: Mapped[date | None] = mapped_column(Date)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    verified_source_id: Mapped[int] = mapped_column(
        ForeignKey("legal_sources.id"), nullable=False
    )

    event: Mapped[Event] = relationship(back_populates="outcomes")
    verified_source: Mapped[LegalSource] = relationship()


class IngestionRun(Base, TimestampMixin):
    __tablename__ = "ingestion_runs"

    def __init__(self, **kwargs):
        """Back-compat initializer for legacy ingestion run fixtures."""
        source_id = kwargs.pop("source_id", None)
        if source_id is not None and "source_name" not in kwargs:
            kwargs["source_name"] = str(source_id)
        kwargs.setdefault("source_name", "unknown")
        super().__init__(**kwargs)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_name: Mapped[str] = mapped_column(String(120), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(80), default=RUNNING)
    fetched_count: Mapped[int] = mapped_column(Integer, default=0)
    parsed_count: Mapped[int] = mapped_column(Integer, default=0)
    persisted_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list | None] = mapped_column(JSON)
    pipeline_stage: Mapped[str | None] = mapped_column(
        String(80), nullable=True, index=True
    )
    quarantine_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # ─── Phase 4: Source Stability & Recovery (retry tracking) ───────────────
    retry_count: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=0
    )  # Number of retry attempts
    scheduled_retry_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )  # When this run should be retried
    recovery_classification: Mapped[str | None] = mapped_column(
        String(20), nullable=True, index=True
    )  # transient, permanent, or unknown
    last_error_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # Timestamp of last error occurrence


class IngestionQueueJob(Base, TimestampMixin):
    """Queue job for ingestion runs (Phase 14)."""

    __tablename__ = "ingestion_queue_jobs"
    __table_args__ = (
        # Unique constraint on (source_key, idempotency_key) for idempotency
        Index('ix_ingestion_queue_jobs_source_key_idempotency_key', 'source_key', 'idempotency_key', unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    job_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    source_key: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(80), nullable=False, index=True, default=PENDING)
    enqueued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    run_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    records_fetched: Mapped[int] = mapped_column(Integer, default=0)
    review_items: Mapped[int] = mapped_column(Integer, default=0)
    created_records: Mapped[int] = mapped_column(Integer, default=0)
    raw_snapshot_preserved: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    retry_count: Mapped[int | None] = mapped_column(Integer, nullable=True, default=0)
    retry_after: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Production-grade concurrency fields
    locked_by: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    dead_lettered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DeadLetterQueueJob(Base, TimestampMixin):
    """Dead-letter queue for failed ingestion jobs (Phase 14)."""

    __tablename__ = "dead_letter_queue_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    original_job_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    job_type: Mapped[str] = mapped_column(String(80), nullable=False)
    payload_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    final_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    dead_lettered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    entity_type: Mapped[str | None] = mapped_column(String(80), index=True)
    entity_id: Mapped[str | None] = mapped_column(String(255), index=True)
    payload: Mapped[dict | None] = mapped_column(JSON)
    actor_ip: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # --- Actor identity fields (Phase 2 hardening) ---
    actor_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    actor_type: Mapped[str | None] = mapped_column(String(80), nullable=True)
    actor_role: Mapped[str | None] = mapped_column(String(80), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # --- Actor auth method (Phase 3 hardening) ---
    actor_auth_method: Mapped[str | None] = mapped_column(String(80), nullable=True)
    # --- Persisted chain integrity fields (Phase 3 hardening) ---
    previous_entry_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    entry_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    before_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    after_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chain_version: Mapped[int | None] = mapped_column(Integer, nullable=True, default=1)


class CrimeIncidentSource(Base):
    __tablename__ = "crime_incident_sources"
    __table_args__ = (
        UniqueConstraint(
            "crime_incident_id", "source_id", name="uq_crime_incident_source"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    crime_incident_id: Mapped[int] = mapped_column(
        ForeignKey("crime_incidents.id"), nullable=False, index=True
    )
    source_id: Mapped[int] = mapped_column(
        ForeignKey("legal_sources.id"), nullable=False, index=True
    )
    relationship_status: Mapped[str] = mapped_column(
        String(80), default="verified_source_link", nullable=False
    )
    supports_claim: Mapped[str | None] = mapped_column(Text)

    incident: Mapped["CrimeIncident"] = relationship(back_populates="source_links")
    source: Mapped["LegalSource"] = relationship()


class CrimeIncidentEventLink(Base):
    __tablename__ = "crime_incident_event_links"
    __table_args__ = (
        UniqueConstraint(
            "crime_incident_id", "event_id", name="uq_crime_incident_event"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    crime_incident_id: Mapped[int] = mapped_column(
        ForeignKey("crime_incidents.id"), nullable=False, index=True
    )
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id"), nullable=False, index=True
    )
    relationship_status: Mapped[str] = mapped_column(
        String(80), default="unverified_context", nullable=False
    )
    link_note: Mapped[str | None] = mapped_column(Text)

    incident: Mapped["CrimeIncident"] = relationship(back_populates="event_links")
    event: Mapped["Event"] = relationship()


class Boundary(Base, TimestampMixin):
    """Simplified administrative boundary from Natural Earth."""

    __tablename__ = "boundaries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    iso_code: Mapped[str | None] = mapped_column(String(10), index=True)
    boundary_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    parent_iso: Mapped[str | None] = mapped_column(String(10))
    source: Mapped[str] = mapped_column(
        String(80), default="natural_earth", nullable=False
    )
    geojson_simplified: Mapped[str | None] = mapped_column(Text)


class AICorrectnessCheck(Base):
    """Structured correctness report for a single map record.

    The AI checks accuracy only — no guilt scores, no judge scores,
    no danger scores, no automated accusations.
    """

    __tablename__ = "ai_correctness_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    record_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    record_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(40), nullable=False)
    event_type_supported: Mapped[bool] = mapped_column(Boolean, nullable=False)
    date_supported: Mapped[bool] = mapped_column(Boolean, nullable=False)
    location_supported: Mapped[bool] = mapped_column(Boolean, nullable=False)
    status_supported: Mapped[bool] = mapped_column(Boolean, nullable=False)
    source_supports_claim: Mapped[bool] = mapped_column(Boolean, nullable=False)
    duplicate_candidate: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False, index=True
    )
    possible_duplicate_ids: Mapped[list | None] = mapped_column(JSON)
    privacy_risk: Mapped[str] = mapped_column(
        String(20), default="low", nullable=False, index=True
    )
    map_quality: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    result_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    findings: Mapped[list["AICorrectnessFinding"]] = relationship(
        back_populates="check", cascade="all, delete-orphan"
    )


class AICorrectnessFinding(Base):
    """Individual finding attached to a correctness check."""

    __tablename__ = "ai_correctness_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    check_id: Mapped[int] = mapped_column(
        ForeignKey("ai_correctness_checks.id"), nullable=False, index=True
    )
    finding_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    field_name: Mapped[str | None] = mapped_column(String(80))
    expected: Mapped[str | None] = mapped_column(Text)
    found: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(20), default="info", nullable=False)
    note: Mapped[str | None] = mapped_column(Text)

    check: Mapped["AICorrectnessCheck"] = relationship(back_populates="findings")


class CLBulkProvenance(Base):
    """One row per record normalized from a CourtListener bulk snapshot.

    Allows every normalized court/case/event/source to be traced back to:
    - CourtListener table and source row ID
    - source CSV file and snapshot date
    - import run ID
    """

    __tablename__ = "cl_bulk_provenance"
    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "cl_table",
            "cl_row_id",
            name="uq_cl_bulk_provenance",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("courtlistener_bulk_runs.id"),
        nullable=False,
        index=True,
    )
    cl_table: Mapped[str] = mapped_column(String(80), nullable=False)
    cl_row_id: Mapped[str] = mapped_column(String(80), nullable=False)
    source_file: Mapped[str] = mapped_column(String(120), nullable=False)
    snapshot_date: Mapped[str] = mapped_column(String(20), nullable=False)
    record_type: Mapped[str] = mapped_column(String(40), nullable=False)
    record_id: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CourtListenerBulkRun(Base):
    """Tracks one file from one CourtListener quarterly snapshot.

    The unique constraint on (snapshot_date, file_name) prevents the
    same file from being imported twice unless force=True is passed,
    which deletes the old row first.
    """

    __tablename__ = "courtlistener_bulk_runs"
    __table_args__ = (
        UniqueConstraint("snapshot_date", "file_name", name="uq_cl_bulk_run"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_date: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    file_name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), default=PENDING, nullable=False, index=True
    )
    rows_read: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_persisted: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rows_skipped: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    errors: Mapped[list | None] = mapped_column(JSON)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SourceSnapshot(Base):
    """Source content snapshots for provenance and archival."""

    __tablename__ = "source_snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_key: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )  # FK-like reference to SourceRegistry.source_key
    source_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    raw_content: Mapped[str | None] = mapped_column(Text)
    extracted_text: Mapped[str | None] = mapped_column(Text)
    http_status: Mapped[int | None] = mapped_column(Integer)
    content_type: Mapped[str | None] = mapped_column(String(255))
    headers_json: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    storage_backend: Mapped[str] = mapped_column(
        String(20), nullable=False, default="db"
    )
    storage_path: Mapped[str | None] = mapped_column(String(1024))
    retention_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Link to ingestion run that created this snapshot
    ingestion_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("ingestion_runs.id"), nullable=True, index=True
    )
    ingestion_run: Mapped["IngestionRun"] = relationship()

    # --- Evidence integrity fields (Phase 1 hardening) ---
    # original_content_hash: hash of full original content, never truncated.
    # Semantically equivalent to content_hash; kept separate for clarity.
    original_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # stored_content_hash: hash of what is actually stored. Must equal
    # original_content_hash after a successful write (no partial evidence).
    stored_content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    content_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stored_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # is_truncated MUST always be False after a successful write.
    # The field is kept for schema compatibility only.
    is_truncated: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", nullable=False
    )
    extractor_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    extractor_version: Mapped[str | None] = mapped_column(String(40), nullable=True)

    # Chain-of-custody log entries for this snapshot
    custody_log: Mapped[list["ChainOfCustodyLog"]] = relationship(
        "ChainOfCustodyLog",
        back_populates="snapshot",
        order_by="ChainOfCustodyLog.created_at",
        cascade="all, delete-orphan",
    )

    def __init__(self, **kwargs):
        """Back-compat initializer for legacy snapshot call-sites/tests."""
        # Legacy callers may pass parser metadata that is no longer persisted here.
        kwargs.pop("parser_version", None)

        legacy_source_quality = kwargs.pop("source_quality", None)

        run_id = kwargs.pop("run_id", None)
        if run_id is not None and "ingestion_run_id" not in kwargs:
            kwargs["ingestion_run_id"] = run_id

        kwargs.pop("snapshot_id", None)
        kwargs.pop("preserved", None)

        source_id = kwargs.pop("source_id", None)
        if source_id is not None and "source_key" not in kwargs:
            kwargs["source_key"] = str(source_id)

        snapshot_hash = kwargs.pop("snapshot_hash", None)
        if snapshot_hash is not None and "content_hash" not in kwargs:
            kwargs["content_hash"] = snapshot_hash

        content = kwargs.pop("content", None)
        if content is not None and "raw_content" not in kwargs:
            kwargs["raw_content"] = content

        snapshot_at = kwargs.pop("snapshot_at", None)
        if snapshot_at is not None and "fetched_at" not in kwargs:
            kwargs["fetched_at"] = snapshot_at

        snapshot_timestamp = kwargs.pop("snapshot_timestamp", None)
        if snapshot_timestamp is not None and "fetched_at" not in kwargs:
            kwargs["fetched_at"] = snapshot_timestamp

        raw_content = kwargs.get("raw_content")
        if isinstance(raw_content, bytes):
            kwargs["raw_content"] = raw_content.decode("utf-8", errors="replace")

        if legacy_source_quality and not kwargs.get("headers_json"):
            kwargs["headers_json"] = (
                '{"source_quality": "' + str(legacy_source_quality).lower() + '"}'
            )

        kwargs.setdefault("source_url", "about:blank")
        kwargs.setdefault("fetched_at", datetime.now(timezone.utc))
        kwargs.setdefault("content_hash", "")

        super().__init__(**kwargs)

    @property
    def source_id(self) -> int | str | None:
        """Back-compat alias for legacy callers that still use source_id."""
        if self.source_key is None:
            return None
        if self.source_key.isdigit():
            return int(self.source_key)
        # Non-numeric source keys should resolve through source_key-based lookups.
        return None

    @source_id.setter
    def source_id(self, value: str | int | None) -> None:
        self.source_key = None if value is None else str(value)

    @property
    def run_id(self) -> int | None:
        """Back-compat alias for legacy callers that still use run_id."""
        return self.ingestion_run_id

    @run_id.setter
    def run_id(self, value: int | None) -> None:
        self.ingestion_run_id = value


class SourceRegistry(Base, TimestampMixin):
    """Registry of ingestion sources with metadata and health tracking."""

    __tablename__ = "source_registry"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_key: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    source_name: Mapped[str] = mapped_column(String(255), nullable=False)
    country: Mapped[str | None] = mapped_column(String(80))
    province_state: Mapped[str | None] = mapped_column(String(80))
    city: Mapped[str | None] = mapped_column(String(120))
    source_type: Mapped[str] = mapped_column(
        String(80), nullable=False, default="unknown"
    )
    source_tier: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        default="news_only_context",
        server_default="news_only_context",
        index=True,
    )
    license: Mapped[str | None] = mapped_column(String(50))
    license_url: Mapped[str | None] = mapped_column(String(2048))
    fetch_method: Mapped[str] = mapped_column(
        String(20), nullable=False, default="manual"
    )
    update_cadence: Mapped[str] = mapped_column(
        String(20), nullable=False, default="manual"
    )
    fields_supported: Mapped[str | None] = mapped_column(Text)
    precision_level: Mapped[str] = mapped_column(
        String(20), nullable=False, default="city_centroid"
    )
    auto_publish_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    requires_manual_review: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    parser_version: Mapped[str | None] = mapped_column(String(20))
    automation_status: Mapped[str | None] = mapped_column(String(30))
    last_successful_fetch: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    last_error: Mapped[str | None] = mapped_column(Text)
    last_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    # Rate limiting and operational controls
    rate_limit_rpm: Mapped[int | None] = mapped_column(
        Integer, default=60
    )  # Requests per minute limit
    last_ingested_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    health_score: Mapped[float] = mapped_column(
        Float, default=1.0, nullable=False
    )  # 0.0-1.0 based on recent success rate
    reliability_score: Mapped[float] = mapped_column(
        Float,
        default=1.0,
        nullable=False,
        server_default="1.0",
    )  # 0.0-1.0 computed from trust tier weight × health_score
    admin_notes: Mapped[str | None] = mapped_column(Text)

    config_json: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)

    # Canada/Saskatchewan-first source metadata fields (migration 0011)
    jurisdiction: Mapped[str | None] = mapped_column(String(120))
    category: Mapped[str | None] = mapped_column(String(80))
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=5, server_default="5"
    )
    enabled_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    public_record_authority: Mapped[str] = mapped_column(
        String(80), nullable=False, default="unknown", server_default="unknown"
    )
    base_url: Mapped[str | None] = mapped_column(String(2048))
    allowed_domains: Mapped[str | None] = mapped_column(Text)  # JSON array
    refresh_interval_minutes: Mapped[int | None] = mapped_column(Integer)
    parser: Mapped[str | None] = mapped_column(String(120))
    creates: Mapped[str | None] = mapped_column(Text)  # JSON array of record types
    public_publish_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    terms_url: Mapped[str | None] = mapped_column(String(2048))
    source_class: Mapped[str | None] = mapped_column(
        String(40)
    )  # 'portal_reference' | 'machine_ingest' | None (legacy = machine_ingest)
    source_status: Mapped[str] = mapped_column(
        String(40),
        nullable=False,
        default="unknown",
        server_default="unknown",
    )

    # ── Lifecycle state fields (migration 0012) ───────────────────────────
    lifecycle_state: Mapped[str | None] = mapped_column(
        String(40)
    )  # see automation_statuses.ALL_LIFECYCLE_STATES
    canonical_replacement_key: Mapped[str | None] = mapped_column(
        String(100)
    )  # populated when lifecycle_state='deprecated'
    status_reason: Mapped[str | None] = mapped_column(
        Text
    )  # human-readable explanation of current state
    operator_next_step: Mapped[str | None] = mapped_column(
        Text
    )  # what an admin must do to advance this source
    section_key: Mapped[str | None] = mapped_column(
        String(80), nullable=True
    )  # logical grouping key for source (e.g. 'provincial_superior_courts')

    # ── Sprint C: provenance / access contract fields (migration 0013) ──────
    confidence_class: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # quality tier: primary_official | secondary_official | tertiary | …
    retention_policy: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # e.g. 'indefinite', '7_years', 'session_only'
    canonical_url: Mapped[str | None] = mapped_column(
        String(2048), nullable=True
    )  # authoritative URL for the source (may differ from base_url)
    evidence_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )  # True = fetch must produce an archived SourceSnapshot before review
    terms_verified: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # ISO date the terms were last verified, or 'false' if not yet done
    authentication_required: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )  # True = adapter needs credentials / API key
    rate_limit_policy: Mapped[str | None] = mapped_column(
        String(50), nullable=True
    )  # e.g. 'polite_1rps', 'bulk_10rps', 'no_limit'

    def __init__(self, **kwargs):
        """Back-compat initializer for legacy fixtures.

        Some tests/builders still pass list values for JSON-like Text columns.
        Normalize those inputs so SQLite can bind them correctly.
        """
        for key in ("allowed_domains", "creates"):
            value = kwargs.get(key)
            if isinstance(value, list):
                kwargs[key] = json.dumps(value)
        super().__init__(**kwargs)


class SourceAdapterContract(Base, TimestampMixin):
    """Registry of adapter parser_version contracts for ingestion validation.
    
    Each SourceAdapter must declare a parser_version. This table tracks which
    versions are active and what schema they enforce. Mismatches between
    IngestionResult.parser_version and the expected version trigger quarantine.
    """

    __tablename__ = "source_adapter_contracts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_key: Mapped[str] = mapped_column(
        String(100), nullable=False, index=True
    )  # FK-like reference to SourceRegistry.source_key (not strict FK to allow deletion)
    parser_version: Mapped[str] = mapped_column(
        String(20), nullable=False, index=True
    )  # e.g. "1.0", "1.1", "2.0"
    adapter_class: Mapped[str] = mapped_column(
        String(120), nullable=False
    )  # Full class path (e.g. "app.ingestion.adapters.SaskCountyCourtsAdapter")
    schema_hash: Mapped[str] = mapped_column(
        String(64), nullable=False
    )  # SHA-256 of expected schema (field names, types, constraints)
    required_fields: Mapped[list | None] = mapped_column(
        JSON, nullable=True
    )  # List of mandatory fields in ParsedRecord
    output_types: Mapped[list | None] = mapped_column(
        JSON, nullable=True
    )  # Types created by this adapter (e.g. ["CrimeIncident", "ReviewItem"])
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", index=True
    )  # "active", "deprecated", "experimental"
    deprecated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    successor_version: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # If deprecated, what version should replace it?
    validation_rules: Mapped[dict | None] = mapped_column(
        JSON, nullable=True
    )  # Custom validation rules (e.g. {"required_confidence_min": 0.7})
    documentation_url: Mapped[str | None] = mapped_column(
        String(2048), nullable=True
    )  # Link to adapter documentation
    created_by: Mapped[str | None] = mapped_column(
        String(120), nullable=True
    )  # Admin who created this contract
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SourceTierConflict(Base, TimestampMixin):
    """Records field-level conflicts detected when a lower-trust source tries
    to overwrite data contributed by a higher-trust source.

    The invariant enforced by conflict_resolution.py is:
        lower trust tier NEVER overwrites higher trust tier
    This table provides an audit trail of every suppressed overwrite.
    """

    __tablename__ = "source_tier_conflicts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # The incoming (lower-trust) source that triggered the conflict
    incoming_source_id: Mapped[int] = mapped_column(
        ForeignKey("source_registry.id", name="fk_stc_incoming_source"),
        nullable=False,
        index=True,
    )
    # The authoritative (higher-trust) source that owns the existing value
    authoritative_source_id: Mapped[int] = mapped_column(
        ForeignKey("source_registry.id", name="fk_stc_authoritative_source"),
        nullable=False,
        index=True,
    )

    # Which model / table the conflict occurred on
    entity_type: Mapped[str] = mapped_column(
        String(80), nullable=False, index=True
    )  # e.g. "crime_incident"
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)

    # Which field conflicted and what the values were
    field_name: Mapped[str] = mapped_column(String(120), nullable=False)
    existing_value: Mapped[str | None] = mapped_column(Text)
    incoming_value: Mapped[str | None] = mapped_column(Text)

    # Resolution outcome
    resolution: Mapped[str] = mapped_column(
        String(20), nullable=False, default="kept_existing"
    )  # "kept_existing" | "accepted_incoming" | "merged"
    resolution_reason: Mapped[str | None] = mapped_column(Text)


class RelationshipEvidence(Base):
    """Stores proof for why two records are linked.

    Prevents false implications by requiring evidence for every relationship.
    Example: "incident linked to court case because docket document X
    names the incident date and charge."
    """

    __tablename__ = "relationship_evidence"

    __table_args__ = (
        UniqueConstraint(
            "from_entity_type",
            "from_entity_id",
            "to_entity_type",
            "to_entity_id",
            "relationship_type",
            name="uq_relationship_evidence_unique_edge",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # The relationship being evidenced
    from_entity_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # "crime_incident", "court_case", "news_article"
    from_entity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    to_entity_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    to_entity_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    relationship_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # "linked_via_docket", "same_incident", "news_context", "judge_presided"

    # The evidence itself
    evidence_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # "docket_text", "police_report", "news_article", "manual_review"
    evidence_source: Mapped[str] = mapped_column(
        String(120), nullable=False, index=True
    )  # source registry key
    evidence_snapshot_id: Mapped[int | None] = mapped_column(
        ForeignKey("source_snapshots.id", name="fk_rel_evidence_snapshot"),
        nullable=True,
        index=True,
    )

    # Evidence content (excerpt or reference)
    evidence_excerpt: Mapped[str | None] = mapped_column(Text)
    evidence_location: Mapped[str | None] = mapped_column(
        String(255)
    )  # Page number, paragraph, URL timestamp

    # Verification
    extracted_by: Mapped[str] = mapped_column(
        String(80), nullable=False
    )  # "crawlee_runner", "ai_linker", "manual_admin"
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    verified_by: Mapped[str | None] = mapped_column(String(120))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Publication visibility and workflow state
    public_visibility: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    verification_status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    relationship_status: Mapped[str | None] = mapped_column(
        String(50), nullable=True, server_default=PENDING
    )
    # Canonical review status used by publication_policy; derived from
    # verification_status / relationship_status at record-promotion time.
    review_status: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="pending_review",
        server_default="pending_review",
        index=True,
    )
    auto_publish_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Relationships
    evidence_snapshot: Mapped["SourceSnapshot"] = relationship()


class CanonicalEntity(Base):
    """Canonical entity for deduplication across sources.

    Represents a unique real-world entity (judge, court, case, defendant,
    incident) that may appear in multiple source records. Links multiple
    source records to a single canonical identity with confidence scoring.
    """

    __tablename__ = "canonical_entities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # "judge", "court", "case", "defendant", "incident"
    canonical_name: Mapped[str] = mapped_column(String(255), nullable=False)
    canonical_id_external: Mapped[str | None] = mapped_column(
        String(255)
    )  # e.g., CourtListener judge ID

    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    merge_confidence: Mapped[float] = mapped_column(
        Float, default=1.0, nullable=False
    )  # 0.0-1.0, confidence in this canonical identity

    confidence_score: Mapped[float | None] = mapped_column(
        Float, nullable=True
    )  # 0.0-1.0, per-entity confidence score used by memory pipeline

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", index=True
    )  # "active", "merged_into", "deprecated"

    merged_into_id: Mapped[int | None] = mapped_column(
        ForeignKey("canonical_entities.id", name="fk_canonical_merged_into"),
        nullable=True,
        index=True,
    )

    # Audit
    created_by: Mapped[str | None] = mapped_column(
        String(120)
    )  # "auto_resolver", admin user ID
    notes: Mapped[str | None] = mapped_column(Text)

    # Relationships
    source_records: Mapped[list["EntitySourceRecord"]] = relationship(
        back_populates="canonical_entity"
    )
    merged_into: Mapped["CanonicalEntity"] = relationship(
        remote_side=[id],
        backref="merged_from",
    )

    def __init__(self, **kwargs):
        """Back-compat initializer for legacy canonical-entity call-sites/tests."""
        name = kwargs.pop("name", None)
        if name is not None and "canonical_name" not in kwargs:
            kwargs["canonical_name"] = name

        external_id = kwargs.pop("external_id", None)
        if external_id is not None and "canonical_id_external" not in kwargs:
            kwargs["canonical_id_external"] = external_id

        # Legacy call-sites passed normalized_name, which is no longer stored.
        kwargs.pop("normalized_name", None)

        legacy_jurisdiction = kwargs.pop("jurisdiction", None)
        confidence = kwargs.pop("confidence", None)
        if confidence is not None and "merge_confidence" not in kwargs:
            kwargs["merge_confidence"] = confidence

        super().__init__(**kwargs)
        self._legacy_jurisdiction = legacy_jurisdiction

    @property
    def jurisdiction(self) -> str | None:
        """Back-compat alias retained for legacy merge-safety checks."""
        return getattr(self, "_legacy_jurisdiction", None)

    @jurisdiction.setter
    def jurisdiction(self, value: str | None) -> None:
        self._legacy_jurisdiction = value


class EntitySourceRecord(Base):
    """Links a source record to its canonical entity.

    Tracks the relationship between a source database record and the
    canonical entity it represents, with confidence and match reasoning.
    """

    __tablename__ = "entity_source_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    canonical_entity_id: Mapped[int] = mapped_column(
        ForeignKey("canonical_entities.id", name="fk_esr_canonical_entity"),
        nullable=False,
        index=True,
    )

    # Source record identification
    source_table: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # "judges", "courts", "cases", "crime_incidents"
    source_record_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source_name: Mapped[str] = mapped_column(
        String(120), nullable=False, index=True
    )  # e.g., "courtlistener", "saskatoon_police"

    # Match metadata
    match_confidence: Mapped[float] = mapped_column(
        Float, default=0.0, nullable=False
    )  # 0.0-1.0
    match_reason: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # "exact_name", "fuzzy_match_95", "manual_link", "external_id"

    # Linking audit
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    linked_by: Mapped[str | None] = mapped_column(
        String(120)
    )  # user ID or "auto_resolver"

    # Verification
    verified_by: Mapped[str | None] = mapped_column(String(120))
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # Relationships
    canonical_entity: Mapped["CanonicalEntity"] = relationship(
        back_populates="source_records"
    )


class EntityGraphEdge(Base):
    """Stores typed relationships between entities as subject-predicate-object triples.

    Enables graph traversal queries without schema changes.
    Example: Judge (subject) presided_over (predicate) Case (object)
    """

    __tablename__ = "entity_graph_edges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Subject (source of relationship)
    subject_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # "judge", "case", "court", "defendant", "incident", "canonical_entity"
    subject_id: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True
    )  # ID in subject table or canonical entity ID

    # Predicate (relationship type)
    predicate: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # "presided_over", "charged_in", "located_at", "appealed_to",
    # "represents", "witnessed", "linked_to", "merged_into"

    # Object (target of relationship)
    object_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # Same enum as subject_type
    object_id: Mapped[int] = mapped_column(
        Integer, nullable=False, index=True
    )  # ID in object table or canonical entity ID

    # Evidence and provenance
    evidence_refs: Mapped[dict | None] = mapped_column(
        JSON
    )  # [{"evidence_id": 1, "confidence": 0.95, "type": "court_record"}]
    source_snapshot_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("source_snapshots.id"), index=True
    )

    # Temporal validity
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )  # When relationship started
    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )  # Null = still valid

    # Audit
    created_by: Mapped[str] = mapped_column(
        String(50), nullable=False, default="ingestion"
    )  # "ingestion", "admin", "ai_suggested", "auto_resolver"
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="active", index=True
    )  # "active", "disputed", "retracted"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Unique constraint to prevent duplicate edges
    __table_args__ = (
        # Unique constraint: same subject, predicate, object at same time
        # Different valid_from allows temporal versioning
        UniqueConstraint(
            "subject_type",
            "subject_id",
            "predicate",
            "object_type",
            "object_id",
            "valid_from",
            name="uq_entity_graph_edge_unique_temporal",
        ),
        {
            "sqlite_autoincrement": True,
        },
    )

    def __init__(self, **kwargs):
        """Back-compat initializer for legacy test fixtures."""
        public_status = kwargs.pop("public_status", None)
        if public_status is not None:
            refs = kwargs.get("evidence_refs")
            if not isinstance(refs, dict):
                refs = {} if refs is None else {"legacy_refs": refs}
            refs["public_status"] = public_status
            kwargs["evidence_refs"] = refs
            if "status" not in kwargs:
                kwargs["status"] = "active" if public_status == "public" else "disputed"

        source_entity_id = kwargs.pop("source_entity_id", None)
        if source_entity_id is not None and "subject_id" not in kwargs:
            kwargs["subject_id"] = source_entity_id

        target_entity_id = kwargs.pop("target_entity_id", None)
        if target_entity_id is not None and "object_id" not in kwargs:
            kwargs["object_id"] = target_entity_id

        edge_type = kwargs.pop("edge_type", None)
        if edge_type is not None and "predicate" not in kwargs:
            kwargs["predicate"] = edge_type

        support_claim_id = kwargs.pop("support_claim_id", None)
        if support_claim_id is not None and "evidence_refs" not in kwargs:
            kwargs["evidence_refs"] = [{"claim_id": support_claim_id}]

        confidence = kwargs.pop("confidence", None)
        if confidence is not None:
            refs = kwargs.setdefault("evidence_refs", [])
            if refs and isinstance(refs[0], dict):
                refs[0].setdefault("confidence", confidence)
            else:
                kwargs["evidence_refs"] = [{"confidence": confidence}]

        kwargs.setdefault("subject_type", "canonical_entity")
        kwargs.setdefault("object_type", "canonical_entity")

        super().__init__(**kwargs)

    @property
    def source_entity_id(self) -> int:
        return self.subject_id

    @source_entity_id.setter
    def source_entity_id(self, value: int) -> None:
        self.subject_id = value

    @property
    def target_entity_id(self) -> int:
        return self.object_id

    @target_entity_id.setter
    def target_entity_id(self, value: int) -> None:
        self.object_id = value

    @property
    def edge_type(self) -> str:
        return self.predicate

    @edge_type.setter
    def edge_type(self, value: str) -> None:
        self.predicate = value

    @property
    def support_claim_id(self) -> int | None:
        refs = self.evidence_refs or []
        if refs and isinstance(refs[0], dict):
            return refs[0].get("claim_id")
        return None

    @hybrid_property
    def public_status(self) -> str:
        refs = self.evidence_refs or {}
        if isinstance(refs, dict):
            explicit = refs.get("public_status")
            if explicit in {"public", "hidden"}:
                return explicit
        return "public" if self.status == "active" else "hidden"

    @public_status.expression
    def public_status(cls):
        explicit = func.json_extract(cls.evidence_refs, "$.public_status")
        return case(
            (explicit == "public", "public"),
            (explicit == "hidden", "hidden"),
            (cls.status == "active", "public"),
            else_="hidden",
        )

    @support_claim_id.setter
    def support_claim_id(self, value: int | None) -> None:
        if value is None:
            return
        refs = self.evidence_refs or []
        if refs and isinstance(refs[0], dict):
            refs[0]["claim_id"] = value
            self.evidence_refs = refs
        else:
            self.evidence_refs = [{"claim_id": value}]

class MemoryRebuildRun(Base, TimestampMixin):
    """Tracks memory rebuild operations."""

    __tablename__ = "memory_rebuild_runs"
    __table_args__ = (
        CheckConstraint(
            "rebuild_scope IN ('full', 'entity')",
            name="ck_memory_rebuild_scope_valid",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rebuild_scope: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="full"
    )
    scope_entity_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("canonical_entities.id"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default=PENDING
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    entities_processed: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )
    claims_created: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )
    claims_invalidated: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )
    states_updated: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    rebuild_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)


class MemoryClaim(Base, TimestampMixin):
    """Individual extracted claims about canonical entities."""

    __tablename__ = "memory_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_key: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True, default=lambda: uuid4().hex
    )
    claim_uid: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, index=True, default=lambda: uuid4().hex
    )
    claim_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    entity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("canonical_entities.id"), nullable=False, index=True
    )
    predicate: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    object_entity_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("canonical_entities.id"), nullable=True, index=True
    )
    object_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    object_value_type: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # enum: entity, literal, date, number, boolean
    normalized_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    claim_value: Mapped[str] = mapped_column(Text, nullable=False)
    claim_value_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0.0", default=0.0
    )
    source_snapshot_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("source_snapshots.id"), nullable=True, index=True
    )
    extraction_model: Mapped[str | None] = mapped_column(String(80), nullable=True)
    extraction_run_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("ingestion_runs.id"), nullable=True
    )
    derived_from_ai: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="false", default=False
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default="true", default=True
    )
    invalidated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    invalidation_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="active",
        default="active",
        index=True,
    )
    review_status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        server_default="pending_review",
        default="pending_review",
        index=True,
    )
    superseded_by_claim_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("memory_claims.id"), nullable=True
    )
    superseded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    jurisdiction: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    valid_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    observed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_quality: Mapped[str | None] = mapped_column(String(80), nullable=True)
    corroboration_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )
    contradiction_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # Dense vector embedding for semantic retrieval (stored as JSON float array).
    # Populated by the embeddings service when JTA_EMBEDDINGS_ENABLED=true.
    claim_embedding: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Claim sensitivity classification for publication policy
    claim_sensitivity: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
        index=True,
    )  # enum: public_record, legal_proceeding, criminal_allegation_named_person, criminal_allegation_private_person, misconduct_allegation, statistical_aggregate, legislation, court_metadata
    publication_sensitivity: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
        index=True,
    )  # enum: public_record, legal_proceeding, criminal_allegation_named_person, criminal_allegation_private_person, misconduct_allegation, statistical_aggregate, legislation, court_metadata
    # Elevated approval fields for sensitive claims
    elevated_review_status: Mapped[str | None] = mapped_column(
        String(20), nullable=True, index=True
    )  # enum: pending_review, approved, rejected
    elevated_reviewer_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    elevated_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __init__(self, **kwargs):
        """Back-compat initializer for legacy tests that reuse placeholder IDs."""
        # Legacy fixtures may still pass source_id on MemoryClaim rows.
        legacy_source_id = kwargs.pop("source_id", None)

        if kwargs.get("claim_value") is None:
            kwargs["claim_value"] = kwargs.get("normalized_value") or kwargs.get("predicate") or kwargs.get("claim_type") or "unspecified"

        claim_key = kwargs.get("claim_key")
        if isinstance(claim_key, str) and claim_key.startswith("test-claim-"):
            kwargs["claim_key"] = f"{claim_key}-{uuid4().hex[:8]}"

        claim_uid = kwargs.get("claim_uid")
        if isinstance(claim_uid, str) and claim_uid.startswith("uid-"):
            kwargs["claim_uid"] = f"{claim_uid}-{uuid4().hex[:8]}"

        super().__init__(**kwargs)
        self._legacy_source_id = legacy_source_id

    @property
    def source_id(self) -> int | str | None:
        """Back-compat alias retained for legacy tests and fixtures."""
        return getattr(self, "_legacy_source_id", None)

    @source_id.setter
    def source_id(self, value: int | str | None) -> None:
        self._legacy_source_id = value


class MemoryEvidenceLink(Base):
    """Links a memory claim to the snapshot that provided evidence."""

    __tablename__ = "memory_evidence_links"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("memory_claims.id"), nullable=False, index=True
    )
    snapshot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("source_snapshots.id"), nullable=False, index=True
    )
    evidence_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    support_type: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )  # enum: supports, contradicts, mentions, context, supersedes
    quote_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    char_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    char_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0.0", default=0.0
    )
    span_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    span_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    span_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        UniqueConstraint("claim_id", "snapshot_id", name="uq_memory_evidence_link"),
    )


class MemoryEntityState(Base, TimestampMixin):
    """Computed per-entity summary derived from active claims."""

    __tablename__ = "memory_entity_states"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("canonical_entities.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    state_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    aliases: Mapped[list | None] = mapped_column(JSON, nullable=True)
    roles: Mapped[list | None] = mapped_column(JSON, nullable=True)
    jurisdictions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    biography_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_rebuild_run_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("memory_rebuild_runs.id"), nullable=True, index=True
    )
    rebuilt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    active_claim_count: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )


class MemoryInvalidation(Base):
    """Immutable audit log of invalidation events."""

    __tablename__ = "memory_invalidations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    invalidation_type: Mapped[str] = mapped_column(
        String(30), nullable=False, index=True
    )
    target_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    reason: Mapped[str] = mapped_column(String(255), nullable=False)
    triggered_by_claim_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("memory_claims.id"), nullable=True, index=True
    )
    triggered_by_rebuild_run_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("memory_rebuild_runs.id"), nullable=True, index=True
    )
    invalidated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class MemoryContradiction(Base):
    """Persistent contradiction records between claims.

    Stores detected contradictions for review and resolution tracking.
    """

    __tablename__ = "memory_contradictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    claim_a_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("memory_claims.id"), nullable=False, index=True
    )
    claim_b_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("memory_claims.id"), nullable=False, index=True
    )
    conflict_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # value_conflict, temporal_overlap, identity_conflict, jurisdiction_conflict, source_conflict, legal_status_conflict
    severity: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="medium", index=True
    )  # low, medium, high, critical
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="open", index=True
    )  # open, reviewing, resolved, false_positive, ignored
    detected_by: Mapped[str] = mapped_column(
        String(50), nullable=False, server_default="system"
    )  # system or user
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    source_authority_weight: Mapped[float] = mapped_column(
        Float, nullable=True
    )  # Authority weight for resolution (higher = more authoritative source)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    reviewer_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "claim_a_id", "claim_b_id", "conflict_type",
            name="uq_memory_contradictions_claims"
        ),
    )

    def __init__(self, **kwargs):
        """Back-compat initializer for legacy contradiction call-sites/tests."""
        conflict_type = kwargs.pop("type", None)
        if conflict_type is not None and "conflict_type" not in kwargs:
            kwargs["conflict_type"] = conflict_type

        kwargs.setdefault("conflict_type", "value_contradiction")
        super().__init__(**kwargs)


class MemoryRelationshipState(Base, TimestampMixin):
    """Computed pairwise relationship state between two canonical entities."""

    __tablename__ = "memory_relationship_states"

    __table_args__ = (
        UniqueConstraint(
            "source_entity_id",
            "target_entity_id",
            "relationship_type",
            name="uq_memory_relationship_state",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_entity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("canonical_entities.id"), nullable=False, index=True
    )
    target_entity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("canonical_entities.id"), nullable=False, index=True
    )
    relationship_type: Mapped[str] = mapped_column(
        String(80), nullable=False, index=True
    )
    state_checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_claim_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0.0", default=0.0
    )
    last_rebuild_run_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("memory_rebuild_runs.id"), nullable=True, index=True
    )
    rebuilt_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class EntityEvidenceLink(Base):
    """Direct link between a canonical entity and a source snapshot.

    Populated during ingestion to record which snapshots contain evidence
    for a given entity. Allows memory rebuild to scope snapshot selection
    to snapshots actually relevant to the entity being rebuilt.
    """

    __tablename__ = "entity_evidence_links"

    __table_args__ = (
        UniqueConstraint("entity_id", "snapshot_id", name="uq_entity_evidence_link"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entity_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("canonical_entities.id"), nullable=False, index=True
    )
    snapshot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("source_snapshots.id"), nullable=False, index=True
    )
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    linking_reason: Mapped[str] = mapped_column(
        String(80), nullable=False, server_default="ingestion_run"
    )


class CourtEvent(Base):
    """Timeline events for court cases.

    Tracks the progression of a case through the justice system:
    filing → hearing → ruling → sentencing → appeal → resolution
    """

    __tablename__ = "court_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # Case linkage
    case_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("cases.id"), nullable=False, index=True
    )

    # Event classification
    event_type: Mapped[str] = mapped_column(
        String(50), nullable=False, index=True
    )  # "filing", "hearing", "ruling", "sentencing", "appeal_filed",
    # "appeal_hearing", "appeal_decision", "probation", "release"
    event_date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    # Event details
    description: Mapped[str | None] = mapped_column(Text)
    outcome: Mapped[str | None] = mapped_column(
        String(50)
    )  # "granted", "denied", "guilty", "not_guilty", "dismissed",
    # "plea_accepted", "convicted", "acquitted", "settled"

    # Entity links (canonical entity IDs)
    judge_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("canonical_entities.id"), index=True
    )  # Presiding judge for this event
    court_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("canonical_entities.id"), index=True
    )  # Court where event occurred

    # Documents and evidence
    documents: Mapped[list[dict] | None] = mapped_column(
        JSON
    )  # [{"url": "...", "type": "ruling", "hash": "sha256..."}]

    # Provenance
    source_snapshot_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("source_snapshots.id"), index=True
    )
    source_url: Mapped[str | None] = mapped_column(String(2048))

    # Audit
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    case: Mapped["Case"] = relationship(back_populates="court_events")
    judge: Mapped["CanonicalEntity | None"] = relationship(foreign_keys=[judge_id])
    court: Mapped["CanonicalEntity | None"] = relationship(foreign_keys=[court_id])


class ChainOfCustodyLog(Base):
    """Immutable audit trail entry for a :class:`SourceSnapshot`.

    Each row records a discrete custody event: creation, access, verification,
    or quarantine.  Rows are append-only; the application must never UPDATE or
    DELETE rows in this table.
    """

    __tablename__ = "chain_of_custody_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    snapshot_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("source_snapshots.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Custody action label.
    # Values: created | accessed | verified | failed_verification |
    #         exported | quarantined
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(120), nullable=False, default="system")
    actor_type: Mapped[str] = mapped_column(
        String(80), nullable=False, default="system"
    )
    # SHA-256 of the content at the time of this event (for later comparison)
    hash_at_event: Mapped[str | None] = mapped_column(String(64))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    snapshot: Mapped["SourceSnapshot"] = relationship(
        "SourceSnapshot", back_populates="custody_log"
    )


class User(Base):
    """Admin user account for JWT-based authentication.

    Replaces the shared-token auth system. Email + hashed password.
    Role controls what admin operations the user can perform.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True, index=True
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(80), nullable=False, default="viewer")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    last_login_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    sessions: Mapped[list["UserSession"]] = relationship(
        "UserSession", back_populates="user", cascade="all, delete-orphan"
    )


class UserSession(Base):
    """Server-side refresh token session record.

    Stores a hashed refresh token so that logout and logout-all can
    revoke individual or all sessions without waiting for JWT expiry.

    Security rules:
    - Only the hash of the refresh token is stored (never the raw token).
    - A revoked session must not allow a new token pair to be issued.
    - An expired session must not allow a new token pair to be issued.
    """

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    refresh_token_hash: Mapped[str] = mapped_column(
        String(128), nullable=False, unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    ip_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)

    user: Mapped["User"] = relationship("User", back_populates="sessions")
