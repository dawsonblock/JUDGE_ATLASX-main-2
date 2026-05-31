"""Add pipeline_stage and quarantine_reason to ingestion_runs.

Revision ID: 20260504_0008
Revises: 20260504_0003
Create Date: 2026-05-04

Adds two nullable columns to ``ingestion_runs`` so the ingestion runner
can record which pipeline stage is currently executing and persist the
reason when a run is quarantined for operator review.

Columns added
-------------
- pipeline_stage    VARCHAR(80) nullable indexed
  Values: fetch | parse | persist | complete | quarantine
- quarantine_reason TEXT nullable
  Human-readable explanation set when pipeline_stage = 'quarantine'

Index
-----
ix_ingestion_runs_pipeline_stage
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260504_0008"
down_revision: Union[str, Sequence[str], None] = "20260504_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "ingestion_runs",
        sa.Column("pipeline_stage", sa.String(80), nullable=True),
    )
    op.add_column(
        "ingestion_runs",
        sa.Column("quarantine_reason", sa.Text(), nullable=True),
    )
    op.create_index(
        "ix_ingestion_runs_pipeline_stage",
        "ingestion_runs",
        ["pipeline_stage"],
    )


def downgrade() -> None:
    op.drop_index("ix_ingestion_runs_pipeline_stage", "ingestion_runs")
    op.drop_column("ingestion_runs", "quarantine_reason")
    op.drop_column("ingestion_runs", "pipeline_stage")
