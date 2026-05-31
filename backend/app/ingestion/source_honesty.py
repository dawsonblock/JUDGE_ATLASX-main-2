"""Source honesty and reliability tracking.

Tracks source reliability over time and provides quality metrics
for source registry entries.
"""

import logging
from typing import Optional, Dict
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from app.models.entities import SourceRegistry

logger = logging.getLogger(__name__)


def _as_utc(dt: datetime) -> datetime:
    """Normalize naive/aware datetimes to UTC-aware for safe arithmetic."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def calculate_source_honesty_score(source_key: str, db: Session) -> float:
    """Calculate honesty score for a source based on reliability metrics.

    Args:
        source_key: Source identifier
        db: Database session

    Returns:
        Honesty score between 0.0 and 1.0
    """
    registry = db.query(SourceRegistry).filter_by(source_key=source_key).first()
    if not registry:
        logger.warning("Source %s not found for honesty calculation", source_key)
        return 0.0

    # Base score from health score
    base_score = registry.health_score or 0.5

    # Adjust for error rate
    error_penalty = 0.0
    if registry.last_error_at:
        days_since_error = (datetime.now(timezone.utc) - _as_utc(registry.last_error_at)).days
        if days_since_error < 1:
            error_penalty = 0.3
        elif days_since_error < 7:
            error_penalty = 0.2
        elif days_since_error < 30:
            error_penalty = 0.1

    # Adjust for consistency (last_successful_fetch vs last_ingested_at)
    consistency_bonus = 0.0
    if registry.last_successful_fetch and registry.last_ingested_at:
        time_diff = abs((_as_utc(registry.last_successful_fetch) - _as_utc(registry.last_ingested_at)).total_seconds())
        if time_diff < 3600:  # Less than 1 hour
            consistency_bonus = 0.1

    # Calculate final score
    honesty_score = base_score - error_penalty + consistency_bonus
    honesty_score = max(0.0, min(1.0, honesty_score))

    return honesty_score


def update_source_reliability_metrics(
    source_key: str,
    success_count: int,
    error_count: int,
    db: Session,
) -> None:
    """Update reliability metrics for a source.

    Args:
        source_key: Source identifier
        success_count: Number of successful operations
        error_count: Number of failed operations
        db: Database session
    """
    registry = db.query(SourceRegistry).filter_by(source_key=source_key).first()
    if not registry:
        logger.warning("Source %s not found for reliability update", source_key)
        return

    # Update reliability counters
    total_ops = success_count + error_count
    if total_ops > 0:
        success_rate = success_count / total_ops

        # Update reliability score using exponential moving average
        if registry.health_score is None:
            registry.health_score = success_rate
        else:
            registry.health_score = 0.8 * registry.health_score + 0.2 * success_rate

    registry.last_ingested_at = datetime.now(timezone.utc)
    db.commit()

    logger.info(
        "Updated reliability metrics for %s: success_rate=%.2f, health_score=%.2f",
        source_key,
        success_count / total_ops if total_ops > 0 else 0,
        registry.health_score,
    )


def get_source_quality_metrics(source_key: str, db: Session) -> Dict[str, any]:
    """Get comprehensive quality metrics for a source.

    Args:
        source_key: Source identifier
        db: Database session

    Returns:
        Dictionary with quality metrics
    """
    registry = db.query(SourceRegistry).filter_by(source_key=source_key).first()
    if not registry:
        return {"error": "Source not found"}

    honesty_score = calculate_source_honesty_score(source_key, db)

    # Calculate uptime percentage (last 30 days)
    uptime_days = 0
    if registry.last_successful_fetch:
        days_since_last_success = (datetime.now(timezone.utc) - _as_utc(registry.last_successful_fetch)).days
        uptime_days = max(0, 30 - days_since_last_success)
    uptime_percentage = uptime_days / 30.0

    # Calculate error frequency
    error_frequency = 0.0
    if registry.last_error_at and registry.last_ingested_at:
        time_span = (_as_utc(registry.last_ingested_at) - _as_utc(registry.last_error_at)).total_seconds()
        if time_span > 0:
            error_frequency = 1.0 / (time_span / 86400)  # Errors per day

    return {
        "source_key": source_key,
        "source_name": registry.source_name,
        "honesty_score": honesty_score,
        "health_score": registry.health_score,
        "uptime_percentage": uptime_percentage,
        "error_frequency": error_frequency,
        "last_successful_fetch": registry.last_successful_fetch.isoformat() if registry.last_successful_fetch else None,
        "last_error": registry.last_error,
        "last_error_at": registry.last_error_at.isoformat() if registry.last_error_at else None,
        "is_active": registry.is_active,
    }


def get_top_reliable_sources(db: Session, limit: int = 10) -> list[Dict[str, any]]:
    """Get top reliable sources based on honesty score.

    Args:
        db: Database session
        limit: Maximum number of sources to return

    Returns:
        List of source quality metrics sorted by honesty score
    """
    sources = db.query(SourceRegistry).filter(SourceRegistry.is_active == True).all()

    metrics_list = []
    for source in sources:
        metrics = get_source_quality_metrics(source.source_key, db)
        metrics_list.append(metrics)

    # Sort by honesty score descending
    metrics_list.sort(key=lambda x: x.get("honesty_score", 0), reverse=True)

    return metrics_list[:limit]


def flag_unreliable_source(source_key: str, db: Session) -> bool:
    """Flag a source as unreliable if its honesty score is too low.

    Args:
        source_key: Source identifier
        db: Database session

    Returns:
        True if source was flagged, False otherwise
    """
    registry = db.query(SourceRegistry).filter_by(source_key=source_key).first()
    if not registry:
        return False

    honesty_score = calculate_source_honesty_score(source_key, db)

    # Flag if honesty score is below threshold
    if honesty_score < 0.5:
        registry.is_active = False
        registry.last_error = f"Flagged as unreliable (honesty_score={honesty_score:.2f})"
        registry.last_error_at = datetime.now(timezone.utc)
        db.commit()
        logger.warning("Flagged source %s as unreliable (score=%.2f)", source_key, honesty_score)
        return True

    return False
