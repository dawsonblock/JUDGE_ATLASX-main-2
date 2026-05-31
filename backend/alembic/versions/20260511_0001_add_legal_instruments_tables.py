"""Add legal_instruments and legal_sections tables.

Revision ID: 20260511_0001
Revises: 20260509_0002
Create Date: 2026-05-11 15:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260511_0001"
down_revision = "20260509_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create legal_instruments table
    op.create_table(
        "legal_instruments",
        sa.Column("id", sa.BIGINT(), autoincrement=True, nullable=False),
        sa.Column("source_id", sa.BIGINT(), nullable=False),
        sa.Column("jurisdiction", sa.VARCHAR(50), nullable=False),
        sa.Column("instrument_type", sa.VARCHAR(50), nullable=False),
        sa.Column("unique_id", sa.VARCHAR(100), nullable=False),
        sa.Column("language", sa.VARCHAR(5), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("short_title", sa.Text(), nullable=True),
        sa.Column("long_title", sa.Text(), nullable=True),
        sa.Column("citation", sa.VARCHAR(255), nullable=True),
        sa.Column("chapter_or_instrument_number", sa.VARCHAR(100), nullable=True),
        sa.Column("current_to_date", sa.DATE(), nullable=True),
        sa.Column("last_amended_date", sa.DATE(), nullable=True),
        sa.Column("in_force_start_date", sa.DATE(), nullable=True),
        sa.Column("consolidated_number", sa.VARCHAR(100), nullable=True),
        sa.Column("link_to_xml", sa.Text(), nullable=True),
        sa.Column("link_to_html_toc", sa.Text(), nullable=True),
        sa.Column("raw_snapshot_id", sa.BIGINT(), nullable=True),
        sa.Column("parser_version", sa.VARCHAR(50), nullable=False, server_default="1.0"),
        sa.Column("review_status", sa.VARCHAR(50), nullable=False, server_default="pending_review"),
        sa.Column("public_visibility", sa.VARCHAR(50), nullable=False, server_default="private"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["source_id"], ["source_registry.id"], name="fk_legal_instruments_source_id"),
        sa.UniqueConstraint("source_id", "unique_id", "language", name="uq_legal_instruments_source_unique_language"),
    )
    
    # Create indexes on legal_instruments
    op.create_index("ix_legal_instruments_jurisdiction", "legal_instruments", ["jurisdiction"])
    op.create_index("ix_legal_instruments_instrument_type", "legal_instruments", ["instrument_type"])
    op.create_index("ix_legal_instruments_review_status", "legal_instruments", ["review_status"])
    op.create_index("ix_legal_instruments_public_visibility", "legal_instruments", ["public_visibility"])
    op.create_index("ix_legal_instruments_source_id", "legal_instruments", ["source_id"])
    
    # Create legal_sections table
    op.create_table(
        "legal_sections",
        sa.Column("id", sa.BIGINT(), autoincrement=True, nullable=False),
        sa.Column("legal_instrument_id", sa.BIGINT(), nullable=False),
        sa.Column("section_label", sa.VARCHAR(50), nullable=False),
        sa.Column("subsection_label", sa.VARCHAR(50), nullable=True),
        sa.Column("marginal_note", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("path", sa.VARCHAR(255), nullable=True),
        sa.Column("historical_note", sa.Text(), nullable=True),
        sa.Column("source_xml_node_id", sa.VARCHAR(100), nullable=True),
        sa.Column("raw_snapshot_id", sa.BIGINT(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["legal_instrument_id"], ["legal_instruments.id"], ondelete="CASCADE", name="fk_legal_sections_legal_instrument_id"),
        sa.UniqueConstraint("legal_instrument_id", "section_label", "subsection_label", name="uq_legal_sections_instrument_label"),
    )
    
    # Create indexes on legal_sections
    op.create_index("ix_legal_sections_legal_instrument_id", "legal_sections", ["legal_instrument_id"])
    op.create_index("ix_legal_sections_section_label", "legal_sections", ["section_label"])


def downgrade() -> None:
    # Drop legal_sections table and indexes
    op.drop_index("ix_legal_sections_section_label", table_name="legal_sections")
    op.drop_index("ix_legal_sections_legal_instrument_id", table_name="legal_sections")
    op.drop_table("legal_sections")
    
    # Drop legal_instruments table and indexes
    op.drop_index("ix_legal_instruments_source_id", table_name="legal_instruments")
    op.drop_index("ix_legal_instruments_public_visibility", table_name="legal_instruments")
    op.drop_index("ix_legal_instruments_review_status", table_name="legal_instruments")
    op.drop_index("ix_legal_instruments_instrument_type", table_name="legal_instruments")
    op.drop_index("ix_legal_instruments_jurisdiction", table_name="legal_instruments")
    op.drop_table("legal_instruments")
