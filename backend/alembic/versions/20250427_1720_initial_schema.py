"""Initial schema migration — matches ORM in app/models/entities.py exactly.

Revision ID: initial
Revises:
Create Date: 2025-04-27 17:20:00.000000

Schema audit completed 2025-04-28; all drift between the original migration
and the ORM has been corrected here.  schema_compat.py is no longer called
on startup for clean installs.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # audit_logs
    # ------------------------------------------------------------------
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("action", sa.String(120), nullable=False, index=True),
        sa.Column("entity_type", sa.String(80), index=True),
        sa.Column("entity_id", sa.String(255), index=True),
        sa.Column("payload", sa.JSON()),
        sa.Column("actor_ip", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # locations
    # ------------------------------------------------------------------
    op.create_table(
        "locations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("location_type", sa.String(80), nullable=False, default="courthouse"),
        sa.Column("city", sa.String(120)),
        sa.Column("state", sa.String(80)),
        sa.Column("region", sa.String(80)),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # courts
    # ------------------------------------------------------------------
    op.create_table(
        "courts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("courtlistener_id", sa.String(32), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("jurisdiction", sa.String(80)),
        sa.Column("region", sa.String(80)),
        sa.Column("location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # judges  (name widened; normalized_name added; legacy fields removed)
    # ------------------------------------------------------------------
    op.create_table(
        "judges",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("normalized_name", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("court_id", sa.Integer(), sa.ForeignKey("courts.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # cases  (docket_number replaces case_number; new fields added)
    # ------------------------------------------------------------------
    op.create_table(
        "cases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("court_id", sa.Integer(), sa.ForeignKey("courts.id"), nullable=False),
        sa.Column("docket_number", sa.String(120), nullable=False),
        sa.Column("normalized_docket_number", sa.String(120), nullable=False),
        sa.Column("caption", sa.String(500), nullable=False),
        sa.Column("case_type", sa.String(80), default="criminal"),
        sa.Column("filed_date", sa.Date()),
        sa.Column("terminated_date", sa.Date()),
        sa.Column("courtlistener_docket_id", sa.String(80), index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint("court_id", "normalized_docket_number", name="uq_case_court_normalized_docket"),
    )

    # ------------------------------------------------------------------
    # defendants  (anonymized_id narrowed; normalized_public_name added)
    # ------------------------------------------------------------------
    op.create_table(
        "defendants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("anonymized_id", sa.String(24), nullable=False, unique=True, index=True),
        sa.Column("public_name", sa.String(255)),
        sa.Column("normalized_public_name", sa.String(255), index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # case_parties  (replaces case_defendants; correct ORM table)
    # ------------------------------------------------------------------
    op.create_table(
        "case_parties",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("defendant_id", sa.Integer(), sa.ForeignKey("defendants.id")),
        sa.Column("party_type", sa.String(80), nullable=False),
        sa.Column("public_name", sa.String(255)),
        sa.Column("normalized_name", sa.String(255), index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint("case_id", "normalized_name", "party_type", name="uq_case_party_name_type"),
    )

    # ------------------------------------------------------------------
    # legal_sources  (url_hash added; source_id narrowed; ORM columns)
    # ------------------------------------------------------------------
    op.create_table(
        "legal_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("source_type", sa.String(80), nullable=False, index=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("api_url", sa.Text()),
        sa.Column("url_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("source_quality", sa.String(80), nullable=False),
        sa.Column("verified_flag", sa.Boolean(), nullable=False, default=False),
        sa.Column("retrieved_at", sa.DateTime(timezone=True)),
        sa.Column("review_status", sa.String(80), nullable=False, default="pending_review", index=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("reviewed_by", sa.String(120)),
        sa.Column("review_notes", sa.Text()),
        sa.Column("correction_note", sa.Text()),
        sa.Column("dispute_note", sa.Text()),
        sa.Column("public_visibility", sa.Boolean(), nullable=False, default=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # events  (full rewrite to match ORM; public_visibility defaults False)
    # ------------------------------------------------------------------
    op.create_table(
        "events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.String(64), nullable=False, unique=True, index=True),
        sa.Column("court_id", sa.Integer(), sa.ForeignKey("courts.id"), nullable=False),
        sa.Column("judge_id", sa.Integer(), sa.ForeignKey("judges.id")),
        sa.Column("case_id", sa.Integer(), sa.ForeignKey("cases.id"), nullable=False),
        sa.Column("primary_location_id", sa.Integer(), sa.ForeignKey("locations.id"), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False, index=True),
        sa.Column("event_subtype", sa.String(120)),
        sa.Column("decision_result", sa.String(120)),
        sa.Column("decision_date", sa.Date(), index=True),
        sa.Column("posted_date", sa.Date()),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("repeat_offender_flag", sa.Boolean(), nullable=False, default=False),
        sa.Column("verified_flag", sa.Boolean(), nullable=False, default=False),
        sa.Column("source_quality", sa.String(80), default="court_record"),
        sa.Column("last_verified_at", sa.DateTime(timezone=True)),
        sa.Column("classifier_metadata", sa.JSON()),
        sa.Column("review_status", sa.String(80), nullable=False, default="pending_review", index=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("reviewed_by", sa.String(120)),
        sa.Column("review_notes", sa.Text()),
        sa.Column("correction_note", sa.Text()),
        sa.Column("dispute_note", sa.Text()),
        sa.Column("public_visibility", sa.Boolean(), nullable=False, default=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # event_defendants
    # ------------------------------------------------------------------
    op.create_table(
        "event_defendants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id"), nullable=False),
        sa.Column("defendant_id", sa.Integer(), sa.ForeignKey("defendants.id"), nullable=False),
        sa.UniqueConstraint("event_id", "defendant_id", name="uq_event_defendant"),
    )

    # ------------------------------------------------------------------
    # topics
    # ------------------------------------------------------------------
    op.create_table(
        "topics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # event_topics
    # ------------------------------------------------------------------
    op.create_table(
        "event_topics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id"), nullable=False),
        sa.Column("topic_id", sa.Integer(), sa.ForeignKey("topics.id"), nullable=False),
        sa.UniqueConstraint("event_id", "topic_id", name="uq_event_topic"),
    )

    # ------------------------------------------------------------------
    # event_sources
    # ------------------------------------------------------------------
    op.create_table(
        "event_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id"), nullable=False),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("legal_sources.id"), nullable=False),
        sa.Column("supports_outcome", sa.Boolean(), nullable=False, default=False),
        sa.UniqueConstraint("event_id", "source_id", name="uq_event_source"),
    )

    # ------------------------------------------------------------------
    # outcomes  (summary NOT NULL; verified_source_id FK added)
    # ------------------------------------------------------------------
    op.create_table(
        "outcomes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id"), nullable=False),
        sa.Column("outcome_type", sa.String(120), nullable=False),
        sa.Column("outcome_date", sa.Date()),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("verified_source_id", sa.Integer(), sa.ForeignKey("legal_sources.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # evidence_reviews  (previous_status/new_status replace decision)
    # ------------------------------------------------------------------
    op.create_table(
        "evidence_reviews",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("entity_type", sa.String(80), nullable=False, index=True),
        sa.Column("entity_id", sa.Integer(), nullable=False, index=True),
        sa.Column("previous_status", sa.String(80)),
        sa.Column("new_status", sa.String(80), nullable=False, index=True),
        sa.Column("reviewed_by", sa.String(120)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("public_visibility", sa.Boolean(), nullable=False, default=False),
    )

    # ------------------------------------------------------------------
    # review_items  (record_type replaces item_type; payload JSON added)
    # ------------------------------------------------------------------
    op.create_table(
        "review_items",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("record_type", sa.String(80), nullable=False, index=True),
        sa.Column("raw_source_id", sa.Integer(), index=True),
        sa.Column("suggested_payload_json", sa.JSON(), nullable=False),
        sa.Column("source_url", sa.Text()),
        sa.Column("source_quality", sa.String(80), nullable=False, index=True),
        sa.Column("confidence", sa.Float(), nullable=False, default=0.0),
        sa.Column("privacy_status", sa.String(80), nullable=False, index=True),
        sa.Column("publish_recommendation", sa.String(80), nullable=False, index=True),
        sa.Column("status", sa.String(80), nullable=False, default="pending", index=True),
        sa.Column("reviewer_id", sa.String(120)),
        sa.Column("reviewer_notes", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
    )

    # ------------------------------------------------------------------
    # review_action_logs  (actor replaces performed_by; before/after JSON)
    # ------------------------------------------------------------------
    op.create_table(
        "review_action_logs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("review_item_id", sa.Integer(), sa.ForeignKey("review_items.id"), nullable=False, index=True),
        sa.Column("actor", sa.String(120), nullable=False),
        sa.Column("action", sa.String(80), nullable=False, index=True),
        sa.Column("before_json", sa.JSON()),
        sa.Column("after_json", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # crime_incidents  (incident_category NOT NULL; review columns added)
    # ------------------------------------------------------------------
    op.create_table(
        "crime_incidents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_id", sa.String(120), index=True),
        sa.Column("external_id", sa.String(120), index=True),
        sa.Column("incident_type", sa.String(120), nullable=False),
        sa.Column("incident_category", sa.String(80), nullable=False, index=True),
        sa.Column("reported_at", sa.DateTime(timezone=True), index=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), index=True),
        sa.Column("city", sa.String(120), index=True),
        sa.Column("province_state", sa.String(120), index=True),
        sa.Column("country", sa.String(80), index=True),
        sa.Column("public_area_label", sa.String(255)),
        sa.Column("latitude_public", sa.Float()),
        sa.Column("longitude_public", sa.Float()),
        sa.Column("precision_level", sa.String(80), nullable=False, default="general_area"),
        sa.Column("source_url", sa.Text()),
        sa.Column("source_name", sa.String(255), nullable=False, index=True),
        sa.Column("verification_status", sa.String(80), nullable=False, default="reported", index=True),
        sa.Column("data_last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("is_public", sa.Boolean(), nullable=False, default=False, index=True),
        sa.Column("notes", sa.Text()),
        sa.Column("review_status", sa.String(80), nullable=False, default="pending_review", index=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("reviewed_by", sa.String(120)),
        sa.Column("review_notes", sa.Text()),
        sa.Column("correction_note", sa.Text()),
        sa.Column("dispute_note", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
        sa.UniqueConstraint("source_name", "external_id", name="uq_crime_incident_source_external"),
    )

    # ------------------------------------------------------------------
    # ingestion_runs  (source_name widened; timestamp columns added)
    # ------------------------------------------------------------------
    op.create_table(
        "ingestion_runs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("source_name", sa.String(120), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(80), default="running"),
        sa.Column("fetched_count", sa.Integer(), default=0),
        sa.Column("parsed_count", sa.Integer(), default=0),
        sa.Column("persisted_count", sa.Integer(), default=0),
        sa.Column("skipped_count", sa.Integer(), default=0),
        sa.Column("error_count", sa.Integer(), default=0),
        sa.Column("errors", sa.JSON()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("ingestion_runs")
    op.drop_table("crime_incidents")
    op.drop_table("review_action_logs")
    op.drop_table("review_items")
    op.drop_table("evidence_reviews")
    op.drop_table("outcomes")
    op.drop_table("event_sources")
    op.drop_table("event_topics")
    op.drop_table("topics")
    op.drop_table("event_defendants")
    op.drop_table("events")
    op.drop_table("legal_sources")
    op.drop_table("case_parties")
    op.drop_table("defendants")
    op.drop_table("cases")
    op.drop_table("judges")
    op.drop_table("courts")
    op.drop_table("locations")
    op.drop_table("audit_logs")
