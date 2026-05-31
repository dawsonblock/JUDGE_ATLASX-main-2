"""Source enablement workflow for enabling real sources one at a time.

Implements controlled source enablement with validation and rollback.
"""

import logging
from typing import Optional, Tuple
from sqlalchemy.orm import Session

from app.models.entities import SourceRegistry
from app.ingestion.source_registry_ctl import (
    can_enable_source,
    require_source_registry,
)

logger = logging.getLogger(__name__)


def enable_source(
    source_key: str,
    enabled_by: str,
    db: Session,
) -> Tuple[bool, str]:
    """Enable a source for ingestion.

    Args:
        source_key: Source identifier
        enabled_by: User or system that enabled the source
        db: Database session

    Returns:
        (success, message) tuple
    """
    registry = require_source_registry(db, source_key)
    can_enable, blockers = can_enable_source(registry)

    if not can_enable:
        blocker_msg = "; ".join(blockers)
        logger.warning("Source %s enable blocked: %s", source_key, blocker_msg)
        return False, f"Enable blocked: {blocker_msg}"

    # Enable the source
    registry.is_active = True
    registry.lifecycle_state = "runnable"
    registry.last_error = None
    registry.last_error_at = None
    db.commit()

    logger.info("Source %s enabled by %s", source_key, enabled_by)
    return True, f"Source {source_key} enabled successfully"


def disable_source(
    source_key: str,
    disabled_by: str,
    db: Session,
    reason: Optional[str] = None,
) -> Tuple[bool, str]:
    """Disable a source from ingestion.

    Args:
        source_key: Source identifier
        disabled_by: User or system that disabled the source
        reason: Reason for disabling
        db: Database session

    Returns:
        (success, message) tuple
    """
    # Back-compat: some callers still pass (source_key, disabled_by, reason, db)
    if not isinstance(db, Session) and isinstance(reason, Session):
        db, reason = reason, db

    registry = db.query(SourceRegistry).filter_by(source_key=source_key).first()
    if not registry:
        return False, f"Source {source_key} not found"

    # Disable the source
    registry.is_active = False
    registry.lifecycle_state = "runnable_disabled"
    registry.last_error = reason or f"Disabled by {disabled_by}"
    db.commit()

    logger.info("Source %s disabled by %s (reason: %s)", source_key, disabled_by, reason)
    return True, f"Source {source_key} disabled successfully"


def validate_source_before_enable(source_key: str, db: Session) -> Tuple[bool, list[str]]:
    """Validate a source before enabling it.

    Args:
        source_key: Source identifier
        db: Database session

    Returns:
        (is_valid, validation_errors) tuple
    """
    registry = require_source_registry(db, source_key)
    can_enable, blockers = can_enable_source(registry)

    if not can_enable:
        return False, blockers

    # Additional validation checks
    errors = []

    # Check if source has required fields
    if not registry.parser:
        errors.append("parser is required")
    if not registry.parser_version:
        errors.append("parser_version is required")
    if not registry.allowed_domains:
        errors.append("allowed_domains is required")
    if not registry.base_url:
        errors.append("base_url is required")

    # Check if source class is appropriate
    if registry.source_class != "machine_ingest":
        errors.append("Only machine_ingest sources can be enabled")

    return len(errors) == 0, errors


def get_next_source_to_enable(db: Session) -> Optional[SourceRegistry]:
    """Get the next source candidate for enablement.

    Prioritizes sources that:
    - Are disabled but have no blockers
    - Have high source tier
    - Have good health scores

    Args:
        db: Database session

    Returns:
        SourceRegistry entry or None
    """
    # Get disabled sources that are enableable
    sources = db.query(SourceRegistry).filter(
        SourceRegistry.is_active == False,
        SourceRegistry.source_class == "machine_ingest",
    ).all()

    candidates = []
    for source in sources:
        can_enable, blockers = can_enable_source(source)
        if can_enable:
            # Score based on tier and health
            tier_score = {"court_record": 3, "official_gov": 2, "news_only_context": 1}
            score = tier_score.get(source.source_tier, 0) + (source.health_score or 0)
            candidates.append((score, source))

    # Sort by score descending
    candidates.sort(key=lambda x: x[0], reverse=True)

    if candidates:
        return candidates[0][1]
    return None


def rollback_source_enablement(
    source_key: str,
    reason: str,
    db: Session,
) -> Tuple[bool, str]:
    """Rollback a source enablement (disable and log).

    Args:
        source_key: Source identifier
        reason: Reason for rollback
        db: Database session

    Returns:
        (success, message) tuple
    """
    return disable_source(source_key, "system_rollback", db, reason)


def batch_enable_sources(
    source_keys: list[str],
    enabled_by: str,
    db: Session,
) -> dict[str, Tuple[bool, str]]:
    """Enable multiple sources in batch.

    Args:
        source_keys: List of source identifiers
        enabled_by: User or system that enabled the sources
        db: Database session

    Returns:
        Dictionary mapping source_key to (success, message) tuple
    """
    results = {}

    for source_key in source_keys:
        success, message = enable_source(source_key, enabled_by, db)
        results[source_key] = (success, message)

        if not success:
            logger.warning("Failed to enable %s: %s", source_key, message)

    return results
