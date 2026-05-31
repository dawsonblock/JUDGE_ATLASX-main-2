"""SourceRegistry integration for ingestion control.

Provides control plane integration with SourceRegistry:
- Check if ingestion is enabled for a source
- Determine review requirements
- Update source health after ingestion runs
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy.orm import Session

from app.models.entities import SourceRegistry
from app.ingestion.statuses import COMPLETED, COMPLETED_WITH_WARNINGS
from app.ingestion.automation_statuses import (
    RUNNABLE_STATUSES,
    ENABLEABLE_STATUSES,
    NON_RUNNABLE_LIFECYCLE_STATES,
    LIFECYCLE_DEPRECATED,
    LIFECYCLE_DISABLED_STUB,
    LIFECYCLE_PORTAL_REFERENCE,
    LIFECYCLE_MANUAL_REFERENCE,
    LIFECYCLE_ADAPTER_MISSING,
    LIFECYCLE_BLOCKED_SECRET,
    LIFECYCLE_RUNNABLE,
    LIFECYCLE_RUNNABLE_DISABLED,
    BLOCK_SOURCE_INACTIVE,
    BLOCK_NO_AUTOMATION_STATUS,
    BLOCK_AUTOMATION_STATUS_PREVENTS_RUN,
    BLOCK_SOURCE_DEPRECATED,
    BLOCK_SOURCE_DISABLED_STUB,
    BLOCK_SOURCE_PORTAL_REFERENCE,
    BLOCK_SOURCE_ADAPTER_MISSING,
    BLOCK_SOURCE_MANUAL_REFERENCE,
    BLOCK_SOURCE_BLOCKED_SECRET,
)

if TYPE_CHECKING:
    from app.models.entities import IngestionRun


def require_source_registry(
    db: Session,
    source_key: str,
    source_name: str | None = None,
) -> SourceRegistry:
    """Require a SourceRegistry entry, failing closed if missing.

    If the source_key doesn't exist, creates a new disabled registry entry
    that must be explicitly enabled by an admin.

    Args:
        db: Database session
        source_key: Unique source identifier (e.g., "courtlistener")
        source_name: Human-readable name (optional)

    Returns:
        SourceRegistry row

    Raises:
        ValueError: If source_key is empty
    """
    if not source_key:
        raise ValueError("source_key is required")

    registry = db.query(SourceRegistry).filter_by(source_key=source_key).first()

    if registry is None:
        # Create disabled entry - fail closed on missing registry
        registry = SourceRegistry(
            source_key=source_key,
            source_name=source_name or source_key,
            source_tier="news_only_context",  # Default to lowest tier
            is_active=False,
            requires_manual_review=True,
            auto_publish_enabled=False,
            last_error=f"Auto-created on {datetime.now(timezone.utc).isoformat()}. "
                       f"Enable explicitly in admin panel.",
        )
        db.add(registry)
        db.commit()
        db.refresh(registry)

    return registry


def check_ingestion_allowed(registry: SourceRegistry) -> tuple[bool, str]:
    """Check if ingestion is allowed for this source.

    Returns:
        (is_allowed, block_reason_code)
        block_reason_code is "ok" when allowed, or a BLOCK_* constant from
        automation_statuses when blocked.
    """
    if not registry.is_active:
        return False, f"{BLOCK_SOURCE_INACTIVE}::source is disabled"

    # lifecycle_state check (highest-priority gate before automation_status)
    lc = registry.lifecycle_state
    if lc is not None:
        if lc == LIFECYCLE_DEPRECATED:
            repl = registry.canonical_replacement_key or "unknown"
            return False, f"{BLOCK_SOURCE_DEPRECATED}::{repl}"
        if lc == LIFECYCLE_DISABLED_STUB:
            return False, BLOCK_SOURCE_DISABLED_STUB
        if lc == LIFECYCLE_PORTAL_REFERENCE:
            return False, BLOCK_SOURCE_PORTAL_REFERENCE
        if lc == LIFECYCLE_MANUAL_REFERENCE:
            return False, BLOCK_SOURCE_MANUAL_REFERENCE
        if lc == LIFECYCLE_ADAPTER_MISSING:
            return False, BLOCK_SOURCE_ADAPTER_MISSING
        if lc == LIFECYCLE_BLOCKED_SECRET:
            return False, BLOCK_SOURCE_BLOCKED_SECRET
        if lc == LIFECYCLE_RUNNABLE_DISABLED:
            # is_active should already be False for these, but belt-and-suspenders:
            return False, BLOCK_AUTOMATION_STATUS_PREVENTS_RUN

    automation_status = registry.automation_status
    if automation_status is None:
        return False, f"{BLOCK_NO_AUTOMATION_STATUS}::no automation_status configured"
    if automation_status not in RUNNABLE_STATUSES:
        return (
            False,
            f"{BLOCK_AUTOMATION_STATUS_PREVENTS_RUN}::{automation_status}",
        )

    return True, "ok"


def is_ingestion_allowed(source_key: str, db: Session) -> bool:
    """Compatibility wrapper returning only boolean allow/deny."""
    registry = require_source_registry(db, source_key)
    allowed, _reason = check_ingestion_allowed(registry)
    return allowed


def get_enable_blockers(registry: SourceRegistry) -> list[str]:
    """Compute lifecycle and configuration blockers for source enablement.

    This function is intentionally shared by admin API and CLI so both paths
    enforce identical readiness policy.
    """
    blockers: list[str] = []

    lifecycle_state = registry.lifecycle_state
    if lifecycle_state == LIFECYCLE_DEPRECATED:
        replacement = registry.canonical_replacement_key or "unknown"
        blockers.append(
            f"{BLOCK_SOURCE_DEPRECATED}: Source is deprecated; use {replacement} instead."
        )
    elif lifecycle_state == LIFECYCLE_DISABLED_STUB:
        blockers.append(
            f"{BLOCK_SOURCE_DISABLED_STUB}: Source is a disabled stub and cannot be enabled."
        )
    elif lifecycle_state == LIFECYCLE_PORTAL_REFERENCE:
        blockers.append(
            f"{BLOCK_SOURCE_PORTAL_REFERENCE}: Source is portal_reference and cannot be machine-enabled."
        )
    elif lifecycle_state == LIFECYCLE_MANUAL_REFERENCE:
        blockers.append(
            f"{BLOCK_SOURCE_MANUAL_REFERENCE}: Source is manual_reference and cannot be machine-enabled."
        )
    elif lifecycle_state == LIFECYCLE_ADAPTER_MISSING:
        blockers.append(
            f"{BLOCK_SOURCE_ADAPTER_MISSING}: Source has no adapter implementation."
        )
    elif lifecycle_state == LIFECYCLE_BLOCKED_SECRET:
        blockers.append(
            f"{BLOCK_SOURCE_BLOCKED_SECRET}: Source is blocked by missing secret configuration."
        )
    elif lifecycle_state == LIFECYCLE_RUNNABLE:
        blockers.append(
            f"{BLOCK_AUTOMATION_STATUS_PREVENTS_RUN}: Source is already runnable; move to runnable_disabled before /enable transition."
        )

    if registry.source_class != "machine_ingest":
        blockers.append("Only machine_ingest sources can be enabled for automated ingestion.")

    if registry.automation_status not in ENABLEABLE_STATUSES:
        blockers.append(
            (
                f"automation_status={registry.automation_status!r} is not enableable; "
                f"must be one of {sorted(ENABLEABLE_STATUSES)}"
            )
        )

    if not registry.parser:
        blockers.append("parser is required")
    if not registry.parser_version:
        blockers.append("parser_version is required")
    if not registry.allowed_domains or registry.allowed_domains in ("[]", ""):
        blockers.append("allowed_domains is required")
    if not registry.base_url:
        blockers.append("base_url is required")
    if getattr(registry, "public_record_authority", None) in (None, "", "unknown"):
        blockers.append("public_record_authority is required")
    if getattr(registry, "terms_url", None) is None:
        blockers.append("terms_url is required")
    if getattr(registry, "requires_manual_review", None) is None:
        blockers.append("requires_manual_review is required")
    if getattr(registry, "public_publish_default", None) is None:
        blockers.append("public_publish_default is required")

    return blockers


def can_enable_source(registry: SourceRegistry) -> tuple[bool, list[str]]:
    """Return enable-readiness and blockers for a source."""
    blockers = get_enable_blockers(registry)
    return len(blockers) == 0, blockers


def update_source_health(
    db: Session,
    source_key: str,
    run: "IngestionRun",
    *,
    auto_commit: bool = True,
) -> None:
    """Update SourceRegistry health metrics after ingestion run.

    Args:
        db: Database session
        source_key: Source identifier
        run: Completed IngestionRun with metrics
        auto_commit: When False, defer commit to caller transaction.
    """
    registry = db.query(SourceRegistry).filter_by(source_key=source_key).first()
    if registry is None:
        return

    now = datetime.now(timezone.utc)
    registry.last_ingested_at = now

    if run.status in (COMPLETED, COMPLETED_WITH_WARNINGS):
        registry.last_successful_fetch = now
        # Clear error if successful
        if run.status == COMPLETED and run.error_count == 0:
            registry.last_error = None
            registry.last_error_at = None
    else:
        registry.last_error = f"Status: {run.status}"
        if run.errors:
            error_msg = str(run.errors[0])
            registry.last_error = f"Status: {run.status}, Error: {error_msg[:200]}"
        registry.last_error_at = now

    # Calculate health score based on recent run success
    total_processed = run.persisted_count + run.skipped_count + run.error_count
    if total_processed > 0:
        success_rate = (run.persisted_count + run.skipped_count) / total_processed
        # Simple health score: blend previous score with new success rate
        if registry.health_score is None:
            registry.health_score = success_rate
        else:
            registry.health_score = 0.7 * registry.health_score + 0.3 * success_rate
    else:
        # No records processed, slight penalty to health score
        registry.health_score = max(0.0, (registry.health_score or 1.0) - 0.1)

    if auto_commit:
        db.commit()


def get_review_requirement(registry: SourceRegistry) -> bool:
    """Determine if records from this source require manual review.

    Returns:
        True if records need admin review before publishing
    """
    return registry.requires_manual_review


def get_auto_publish_policy(registry: SourceRegistry) -> bool:
    """Determine if records should be auto-published after review.

    Returns:
        True if records should auto-publish (when review passes)
    """
    return registry.auto_publish_enabled
