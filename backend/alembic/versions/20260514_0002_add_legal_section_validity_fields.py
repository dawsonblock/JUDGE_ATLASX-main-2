"""Add validity and activity fields to legal_sections and legal_section_revisions.

Revision ID: 20260514_0002
Revises: 20260514_0001
Create Date: 2026-05-14 10:30:00.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260514_0002"
down_revision = "20260514_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # legal_sections: validity window + active flag + supersession pointer
    op.add_column(
        "legal_sections",
        sa.Column("valid_from", sa.Date(), nullable=True),
    )
    op.add_column(
        "legal_sections",
        sa.Column("valid_to", sa.Date(), nullable=True),
    )
    op.add_column(
        "legal_sections",
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "legal_sections",
        sa.Column("superseded_by_section_key", sa.String(length=80), nullable=True),
    )

    # legal_section_revisions: validity start + change classification
    op.add_column(
        "legal_section_revisions",
        sa.Column("valid_from", sa.Date(), nullable=True),
    )
    op.add_column(
        "legal_section_revisions",
        sa.Column("change_type", sa.String(length=40), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("legal_section_revisions", "change_type")
    op.drop_column("legal_section_revisions", "valid_from")
    op.drop_column("legal_sections", "superseded_by_section_key")
    op.drop_column("legal_sections", "is_active")
    op.drop_column("legal_sections", "valid_to")
    op.drop_column("legal_sections", "valid_from")
