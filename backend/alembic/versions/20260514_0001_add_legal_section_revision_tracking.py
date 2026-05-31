"""Add legal section key/hash/version and revision history table.

Revision ID: 20260514_0001
Revises: 20260512_0001
Create Date: 2026-05-14 09:00:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260514_0001"
down_revision = "20260512_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("legal_sections", sa.Column("section_key", sa.String(length=80), nullable=True))
    op.add_column("legal_sections", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.add_column(
        "legal_sections",
        sa.Column("text_version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("ix_legal_sections_section_key", "legal_sections", ["section_key"])
    op.create_index("ix_legal_sections_content_hash", "legal_sections", ["content_hash"])

    op.create_table(
        "legal_section_revisions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("legal_section_id", sa.BigInteger(), nullable=False),
        sa.Column("revision_number", sa.Integer(), nullable=False),
        sa.Column("previous_content_hash", sa.String(length=64), nullable=True),
        sa.Column("new_content_hash", sa.String(length=64), nullable=False),
        sa.Column("diff_summary", sa.Text(), nullable=True),
        sa.Column("raw_snapshot_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["legal_section_id"], ["legal_sections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["raw_snapshot_id"], ["source_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "legal_section_id",
            "revision_number",
            name="uq_legal_section_revisions_section_revision",
        ),
    )
    op.create_index(
        "ix_legal_section_revisions_legal_section_id",
        "legal_section_revisions",
        ["legal_section_id"],
    )
    op.create_index(
        "ix_legal_section_revisions_previous_content_hash",
        "legal_section_revisions",
        ["previous_content_hash"],
    )
    op.create_index(
        "ix_legal_section_revisions_new_content_hash",
        "legal_section_revisions",
        ["new_content_hash"],
    )


def downgrade() -> None:
    op.drop_index("ix_legal_section_revisions_new_content_hash", table_name="legal_section_revisions")
    op.drop_index("ix_legal_section_revisions_previous_content_hash", table_name="legal_section_revisions")
    op.drop_index("ix_legal_section_revisions_legal_section_id", table_name="legal_section_revisions")
    op.drop_table("legal_section_revisions")

    op.drop_index("ix_legal_sections_content_hash", table_name="legal_sections")
    op.drop_index("ix_legal_sections_section_key", table_name="legal_sections")
    op.drop_column("legal_sections", "text_version")
    op.drop_column("legal_sections", "content_hash")
    op.drop_column("legal_sections", "section_key")
