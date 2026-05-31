"""Phase 4: Source Stability & Recovery - Add Retry Tracking

Alembic migration to add fields for retry tracking and recovery management.

Adds to IngestionRun:
- retry_count: Track number of retry attempts
- scheduled_retry_at: When this run should be retried
- recovery_classification: Transient/permanent error classification
- last_error_at: Timestamp of last error occurrence
"""

from alembic import op
import sqlalchemy as sa


# Revision identifiers, used by Alembic.
revision = "20260516_0004"
down_revision = "20260516_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add Phase 4 recovery tracking fields to IngestionRun."""
    
    # Add fields to ingestion_runs table
    op.add_column(
        "ingestion_runs",
        sa.Column(
            "retry_count",
            sa.Integer,
            nullable=True,
            default=0,
            server_default="0",
            comment="Number of retry attempts for this run",
        ),
    )
    
    op.add_column(
        "ingestion_runs",
        sa.Column(
            "scheduled_retry_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="When this run should be retried (if transient error)",
        ),
    )
    
    op.add_column(
        "ingestion_runs",
        sa.Column(
            "recovery_classification",
            sa.String(20),
            nullable=True,
            comment="Error classification: transient, permanent, or unknown",
        ),
    )
    
    op.add_column(
        "ingestion_runs",
        sa.Column(
            "last_error_at",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Timestamp when last error occurred in this run",
        ),
    )
    
    # Create index on scheduled_retry_at for efficient query of pending retries
    op.create_index(
        "ix_ingestion_runs_scheduled_retry_at",
        "ingestion_runs",
        ["scheduled_retry_at"],
        mysql_length=None,
    )
    
    # Create index on recovery_classification for filtering by error type
    op.create_index(
        "ix_ingestion_runs_recovery_classification",
        "ingestion_runs",
        ["recovery_classification"],
        mysql_length=None,
    )


def downgrade() -> None:
    """Remove Phase 4 recovery tracking fields."""
    
    # Drop indices
    op.drop_index("ix_ingestion_runs_recovery_classification", table_name="ingestion_runs")
    op.drop_index("ix_ingestion_runs_scheduled_retry_at", table_name="ingestion_runs")
    
    # Drop columns
    op.drop_column("ingestion_runs", "last_error_at")
    op.drop_column("ingestion_runs", "recovery_classification")
    op.drop_column("ingestion_runs", "scheduled_retry_at")
    op.drop_column("ingestion_runs", "retry_count")
