"""Phase 4: Dead-Letter Queue for Quarantined Ingestions

Manages quarantined and failed IngestionRun records, providing recovery
interfaces for admin intervention and automatic retry scheduling.

A "dead-letter" record is an IngestionRun that has exhausted retry attempts or
encountered a permanent error. Dead-letter records are stored with full context
(errors, last_error_at, quarantine_reason) to enable post-mortem analysis and
targeted recovery.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

from sqlalchemy import and_, desc
from sqlalchemy.orm import Session

from app.ingestion.recovery_strategies import (
    classify_error,
    ErrorCategory,
)
from app.ingestion.statuses import FAILED, QUARANTINED
from app.models.entities import IngestionRun, SourceRegistry

if TYPE_CHECKING:
    pass


class DeadLetterQueue:
    """Interface for querying and recovering from the dead-letter queue."""

    def __init__(self, db: Session):
        """Initialize dead-letter queue with database session."""
        self.db = db

    def list_quarantined_runs(
        self,
        source_key: str | None = None,
        limit: int = 100,
        offset: int = 0,
        min_age_hours: int | None = None,
    ) -> list[dict]:
        """List quarantined and failed IngestionRun records.

        Args:
            source_key: Filter by source (optional)
            limit: Maximum number of records to return
            offset: Pagination offset
            min_age_hours: Filter to runs at least this old (useful to skip recent failures)

        Returns:
            List of dicts with run metadata suitable for admin UI/API
        """
        query = self.db.query(IngestionRun).filter(
            IngestionRun.status.in_([QUARANTINED, FAILED])
        )

        if source_key:
            query = query.filter(IngestionRun.source_name == source_key)

        if min_age_hours is not None:
            cutoff = datetime.now(timezone.utc) - timedelta(hours=min_age_hours)
            query = query.filter(IngestionRun.created_at <= cutoff)

        # Most recent failures first
        query = query.order_by(desc(IngestionRun.created_at))
        query = query.limit(limit).offset(offset)

        runs = query.all()
        return [
            {
                "id": run.id,
                "source_name": run.source_name,
                "status": run.status,
                "quarantine_reason": run.quarantine_reason,
                "error_count": run.error_count,
                "errors": run.errors,
                "created_at": run.created_at.isoformat() if run.created_at else None,
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "pipeline_stage": run.pipeline_stage,
                "last_error_at": run.last_error_at.isoformat() if hasattr(run, 'last_error_at') and run.last_error_at else None,
                "retry_count": getattr(run, "retry_count", None),
            }
            for run in runs
        ]

    def classify_dead_letter(self, run: IngestionRun) -> dict:
        """Analyze a dead-letter run to determine recovery options.

        Returns dict with:
        - error_category: transient, permanent, unknown
        - retriable: boolean indicating if automatic retry is possible
        - suggested_action: 'auto_retry', 'manual_intervention', 'skip'
        - recovery_reason: human-readable explanation
        """
        if not run.errors:
            return {
                "error_category": "unknown",
                "retriable": False,
                "suggested_action": "manual_intervention",
                "recovery_reason": "No errors recorded; requires admin review",
            }

        error_msg = str(run.errors[0]) if isinstance(run.errors, list) else str(run.errors)
        classification = classify_error(error_msg)

        return {
            "error_category": classification.category.value,
            "retriable": classification.retriable,
            "suggested_action": (
                "auto_retry"
                if classification.retriable
                else "manual_intervention"
            ),
            "recovery_reason": classification.reason,
        }

    def schedule_retry(
        self,
        run_id: int,
        scheduled_for: datetime | None = None,
    ) -> bool:
        """Schedule a quarantined run for retry.

        Updates the IngestionRun with a scheduled retry time. The actual retry
        will be picked up by the ingestion scheduler.

        Args:
            run_id: ID of the IngestionRun to retry
            scheduled_for: When to retry (default: now)

        Returns:
            True if scheduling succeeded, False if run not found or not retriable
        """
        run = self.db.query(IngestionRun).filter_by(id=run_id).first()
        if run is None:
            return False

        # Check if it's actually retriable
        classification = self.classify_dead_letter(run)
        if not classification["retriable"]:
            return False

        # Update retry count
        if not hasattr(run, "retry_count") or run.retry_count is None:
            run.retry_count = 1
        else:
            run.retry_count += 1

        # Set scheduled retry time
        if not hasattr(run, "scheduled_retry_at"):
            run.scheduled_retry_at = scheduled_for or datetime.now(timezone.utc)
        else:
            run.scheduled_retry_at = scheduled_for or datetime.now(timezone.utc)

        # Reset status to allow re-queuing
        run.status = "pending_retry"

        self.db.commit()
        return True

    def get_recovery_runbook(self, run: IngestionRun) -> str:
        """Generate a recovery runbook for this failed ingestion.

        Returns a human-readable guide for admin intervention based on the
        failure classification.
        """
        if not run.errors:
            return (
                "No error details available.\n"
                "1. Check SourceRegistry status for this source\n"
                "2. Verify adapter configuration\n"
                "3. Run adapter validation tests\n"
            )

        error_msg = str(run.errors[0]) if isinstance(run.errors, list) else str(run.errors)
        classification = classify_error(error_msg)

        if classification.category == ErrorCategory.TRANSIENT:
            return (
                f"Transient Error Detected: {error_msg[:100]}\n"
                "Recovery Steps:\n"
                f"1. Source will auto-retry with exponential backoff\n"
                f"2. Current retry count: {getattr(run, 'retry_count', 0)}\n"
                f"3. If retries exhausted, check source health score\n"
                f"4. Verify network/service availability before manual retry\n"
            )

        if classification.category == ErrorCategory.PERMANENT:
            return (
                f"Permanent Error Detected: {error_msg[:100]}\n"
                "Recovery Steps:\n"
                f"1. Source does not auto-retry (permanent error)\n"
                f"2. Review adapter configuration and contract\n"
                f"3. Validate source data/schema\n"
                f"4. Check parser version compatibility\n"
                f"5. Fix underlying issue, then manually schedule retry\n"
            )

        return (
            f"Unclassified Error: {error_msg[:100]}\n"
            "Recovery Steps:\n"
            "1. Review error message carefully\n"
            "2. Check source logs and adapter output\n"
            "3. Verify source is accessible and responding\n"
            "4. Consult adapter documentation\n"
            "5. Contact source provider if needed\n"
        )

    def count_quarantined_by_source(self) -> dict[str, int]:
        """Count quarantined runs grouped by source."""
        from sqlalchemy import func

        results = (
            self.db.query(
                IngestionRun.source_name,
                func.count(IngestionRun.id).label("count"),
            )
            .filter(IngestionRun.status.in_([QUARANTINED, FAILED]))
            .group_by(IngestionRun.source_name)
            .all()
        )

        return {source: count for source, count in results}

    def get_recovery_summary(self) -> dict:
        """Get summary statistics for dead-letter queue monitoring."""
        from sqlalchemy import func

        total_quarantined = (
            self.db.query(func.count(IngestionRun.id))
            .filter(IngestionRun.status.in_([QUARANTINED, FAILED]))
            .scalar()
        )

        total_failed = (
            self.db.query(func.count(IngestionRun.id))
            .filter(IngestionRun.status == FAILED)
            .scalar()
        )

        total_quarantined_only = (
            self.db.query(func.count(IngestionRun.id))
            .filter(IngestionRun.status == QUARANTINED)
            .scalar()
        )

        # Transient errors (retriable)
        runs = self.db.query(IngestionRun).filter(
            IngestionRun.status.in_([QUARANTINED, FAILED])
        ).all()

        transient_count = 0
        for run in runs:
            classification = self.classify_dead_letter(run)
            if classification["retriable"]:
                transient_count += 1

        return {
            "total_quarantined": total_quarantined or 0,
            "failed_runs": total_failed or 0,
            "quarantined_runs": total_quarantined_only or 0,
            "retriable_count": transient_count,
            "quarantined_by_source": self.count_quarantined_by_source(),
        }
