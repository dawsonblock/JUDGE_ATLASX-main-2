"""Remove dead models: topics and event_topics tables.

Revision ID: 20260504_0009
Revises: 20260504_0008
Create Date: 2026-05-04 00:09:00.000000

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = "20260504_0009"
down_revision = "20260504_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # event_topics has FK to topics — drop it first
    op.drop_table("event_topics")
    op.drop_table("topics")


def downgrade() -> None:
    op.create_table(
        "topics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "event_topics",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("event_id", sa.Integer(), nullable=False),
        sa.Column("topic_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["event_id"], ["events.id"]),
        sa.ForeignKeyConstraint(["topic_id"], ["topics.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("event_id", "topic_id", name="uq_event_topic"),
    )
