"""Add public_visibility, verification_status, relationship_status, auto_publish_reason to relationship_evidence.

Revision ID: 20260503_0002
Revises: 20260503_0001
Create Date: 2026-05-03
"""

import sqlalchemy as sa
from alembic import op

revision = "20260503_0002"
down_revision = "20260503_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "relationship_evidence",
        sa.Column(
            "public_visibility",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "relationship_evidence",
        sa.Column("verification_status", sa.String(50), nullable=True),
    )
    op.add_column(
        "relationship_evidence",
        sa.Column(
            "relationship_status",
            sa.String(50),
            nullable=True,
            server_default="pending",
        ),
    )
    op.add_column(
        "relationship_evidence",
        sa.Column("auto_publish_reason", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("relationship_evidence", "auto_publish_reason")
    op.drop_column("relationship_evidence", "relationship_status")
    op.drop_column("relationship_evidence", "verification_status")
    op.drop_column("relationship_evidence", "public_visibility")
