"""Add crime_incident_sources and crime_incident_event_links tables.

Revision ID: add_incident_link_tables
Revises: initial
Create Date: 2026-04-28 00:01:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "add_incident_link_tables"
down_revision: Union[str, Sequence[str], None] = "initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "crime_incident_sources",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("crime_incident_id", sa.Integer(), sa.ForeignKey("crime_incidents.id"), nullable=False, index=True),
        sa.Column("source_id", sa.Integer(), sa.ForeignKey("legal_sources.id"), nullable=False, index=True),
        sa.Column("relationship_status", sa.String(80), nullable=False, default="verified_source_link"),
        sa.Column("supports_claim", sa.Text()),
        sa.UniqueConstraint("crime_incident_id", "source_id", name="uq_crime_incident_source"),
    )
    op.create_table(
        "crime_incident_event_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("crime_incident_id", sa.Integer(), sa.ForeignKey("crime_incidents.id"), nullable=False, index=True),
        sa.Column("event_id", sa.Integer(), sa.ForeignKey("events.id"), nullable=False, index=True),
        sa.Column("relationship_status", sa.String(80), nullable=False, default="unverified_context"),
        sa.Column("link_note", sa.Text()),
        sa.UniqueConstraint("crime_incident_id", "event_id", name="uq_crime_incident_event"),
    )


def downgrade() -> None:
    op.drop_table("crime_incident_event_links")
    op.drop_table("crime_incident_sources")
