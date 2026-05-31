"""Reviewer dashboard metrics and analytics.

Provides metrics for reviewer performance and workflow analytics.
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import func, select

from app.models.entities import (
    ReviewItem,
    ReviewActionLog,
    EvidenceReview,
    CrimeIncident,
    LegalInstrument,
    LegalSource,
    Event,
)

logger = logging.getLogger(__name__)


def get_reviewer_metrics(
    db: Session,
    reviewer_id: Optional[str] = None,
    days: int = 30,
) -> Dict[str, Any]:
    """Get metrics for a reviewer or overall review performance.

    Args:
        db: Database session
        reviewer_id: Optional reviewer ID to filter by
        days: Number of days to look back

    Returns:
        Dictionary of review metrics
    """
    since_date = datetime.now(timezone.utc) - timedelta(days=days)

    # Base query for review actions
    action_query = select(ReviewActionLog).where(
        ReviewActionLog.created_at >= since_date
    )

    if reviewer_id:
        action_query = action_query.where(ReviewActionLog.actor == reviewer_id)

    total_actions = db.scalar(select(func.count()).select_from(action_query.subquery())) or 0

    # Get approved/rejected counts
    approved_count = db.scalar(
        select(func.count())
        .select_from(action_query.where(ReviewActionLog.action == "approved").subquery())
    ) or 0

    rejected_count = db.scalar(
        select(func.count())
        .select_from(action_query.where(ReviewActionLog.action == "rejected").subquery())
    ) or 0

    # Get average time to review
    review_logs = db.scalars(action_query).all()
    avg_review_time = _calculate_avg_review_time(review_logs)

    return {
        "total_reviews": total_actions,
        "approved_count": approved_count,
        "rejected_count": rejected_count,
        "approval_rate": approved_count / total_actions if total_actions > 0 else 0.0,
        "avg_review_time_seconds": avg_review_time,
        "period_days": days,
    }


def get_queue_metrics(db: Session) -> Dict[str, Any]:
    """Get metrics about the review queue.

    Args:
        db: Database session

    Returns:
        Dictionary of queue metrics
    """
    # Count pending items by type
    pending_events = (
        db.scalar(select(func.count()).select_from(
            select(Event).where(Event.review_status == "pending_review").subquery()
        )) or 0
    )

    pending_incidents = (
        db.scalar(select(func.count()).select_from(
            select(CrimeIncident).where(CrimeIncident.review_status == "pending_review").subquery()
        )) or 0
    )

    pending_instruments = (
        db.scalar(select(func.count()).select_from(
            select(LegalInstrument).where(LegalInstrument.review_status == "pending_review").subquery()
        )) or 0
    )

    pending_sources = (
        db.scalar(select(func.count()).select_from(
            select(LegalSource).where(LegalSource.review_status == "pending_review").subquery()
        )) or 0
    )

    total_pending = pending_events + pending_incidents + pending_instruments + pending_sources

    # Get recently approved items
    since_yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    recent_approvals = (
        db.scalar(select(func.count()).select_from(
            select(EvidenceReview).where(
                EvidenceReview.reviewed_at >= since_yesterday,
                EvidenceReview.new_status == "approved",
            ).subquery()
        )) or 0
    )

    return {
        "pending_events": pending_events,
        "pending_incidents": pending_incidents,
        "pending_instruments": pending_instruments,
        "pending_sources": pending_sources,
        "total_pending": total_pending,
        "recent_approvals_24h": recent_approvals,
    }


def get_review_trend(
    db: Session,
    days: int = 30,
    bucket_days: int = 7,
) -> List[Dict[str, Any]]:
    """Get review trend data over time.

    Args:
        db: Database session
        days: Number of days to look back
        bucket_days: Number of days per bucket

    Returns:
        List of time-bucketed metrics
    """
    since_date = datetime.now(timezone.utc) - timedelta(days=days)
    buckets = []

    for i in range(0, days, bucket_days):
        bucket_start = since_date + timedelta(days=i)
        bucket_end = bucket_start + timedelta(days=bucket_days)

        # Count reviews in this bucket
        bucket_count = (
            db.scalar(select(func.count()).select_from(
                select(EvidenceReview).where(
                    EvidenceReview.reviewed_at >= bucket_start,
                    EvidenceReview.reviewed_at < bucket_end,
                ).subquery()
            )) or 0
        )

        buckets.append({
            "period_start": bucket_start.isoformat(),
            "period_end": bucket_end.isoformat(),
            "review_count": bucket_count,
        })

    return buckets


def get_top_reviewers(db: Session, days: int = 30, limit: int = 10) -> List[Dict[str, Any]]:
    """Get top reviewers by review count.

    Args:
        db: Database session
        days: Number of days to look back
        limit: Maximum number of reviewers to return

    Returns:
        List of reviewer metrics
    """
    since_date = datetime.now(timezone.utc) - timedelta(days=days)

    # Group by reviewer and count
    reviewer_counts = (
        db.query(
            ReviewActionLog.actor,
            func.count(ReviewActionLog.id).label("count"),
        )
        .where(ReviewActionLog.created_at >= since_date)
        .group_by(ReviewActionLog.actor)
        .order_by(func.count(ReviewActionLog.id).desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "reviewer_id": actor,
            "review_count": count,
            "period_days": days,
        }
        for actor, count in reviewer_counts
    ]


def _calculate_avg_review_time(review_logs: List[ReviewActionLog]) -> Optional[float]:
    """Calculate average time to review in seconds.

    Args:
        review_logs: List of review action logs

    Returns:
        Average review time in seconds, or None if not calculable
    """
    if not review_logs:
        return None

    times = []
    for log in review_logs:
        # Try to get time from review item creation to action
        if log.review_item_id:
            # This would need to join with ReviewItem to get created_at
            # For now, return None as this requires more complex query
            pass

    return None if not times else sum(times) / len(times)


def get_workflow_health(db: Session) -> Dict[str, Any]:
    """Get overall workflow health metrics.

    Args:
        db: Database session

    Returns:
        Dictionary of health metrics
    """
    # Get queue metrics
    queue_metrics = get_queue_metrics(db)

    # Get recent activity
    since_yesterday = datetime.now(timezone.utc) - timedelta(days=1)
    recent_activity = (
        db.scalar(select(func.count()).select_from(
            select(ReviewActionLog).where(
                ReviewActionLog.created_at >= since_yesterday
            ).subquery()
        )) or 0
    )

    # Calculate health score
    health_score = 1.0
    if queue_metrics["total_pending"] > 100:
        health_score -= 0.2
    if recent_activity < 10:
        health_score -= 0.3

    health_score = max(0.0, min(1.0, health_score))

    return {
        "queue_size": queue_metrics["total_pending"],
        "recent_activity_24h": recent_activity,
        "health_score": health_score,
        "healthy": health_score >= 0.7,
    }
