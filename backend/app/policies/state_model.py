"""Canonical state model for publication, review decisions, and memory states.

This module is intentionally additive and compatibility-focused. It does not
replace existing ``review_status`` strings yet; it provides typed enums and
mapper helpers so callers can migrate incrementally.
"""

from __future__ import annotations

from enum import Enum


class PublicationState(str, Enum):
    """Canonical publication lifecycle state for user-facing entities."""

    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    PUBLISHED = "published"
    RESTRICTED = "restricted"
    ARCHIVED = "archived"


class ArchivePublicationStatus(str, Enum):
    """Archive/export publication status used in custody JSONL records."""

    UNPUBLISHED = "unpublished"
    PUBLIC = "public"
    RESTRICTED = "restricted"
    ARCHIVED = "archived"


class ReviewDecision(str, Enum):
    """Canonical reviewer actions used by moderation workflows."""

    APPROVE = "approve"
    REJECT = "reject"
    CORRECT = "correct"
    DISPUTE = "dispute"
    REMOVE = "remove"


class ReviewQueueDecision(str, Enum):
    """Internal ReviewItem workflow decisions."""

    APPROVED = "approved"
    REJECTED = "rejected"
    FLAGGED = "flagged"


def normalize_review_decision(
    value: str | ReviewDecision | None,
) -> ReviewDecision | None:
    """Normalize raw decision input into :class:`ReviewDecision`.

    Returns ``None`` when the value is missing or not a known decision.
    """
    if value is None:
        return None
    if isinstance(value, ReviewDecision):
        return value
    try:
        return ReviewDecision(str(value).strip().lower())
    except ValueError:
        return None


def normalize_review_queue_decision(
    value: str | ReviewQueueDecision | None,
) -> ReviewQueueDecision | None:
    """Normalize raw ReviewItem decision input.

    Returns ``None`` when the value is missing or unknown.
    """
    if value is None:
        return None
    if isinstance(value, ReviewQueueDecision):
        return value
    try:
        return ReviewQueueDecision(str(value).strip().lower())
    except ValueError:
        return None


class MemoryLifecycleState(str, Enum):
    """Lifecycle state of derivative memory records."""

    EXTRACTED = "extracted"
    INDEXED = "indexed"
    CACHED = "cached"
    VALIDATED = "validated"
    RETRACTED = "retracted"


class MemoryConfidenceState(str, Enum):
    """Confidence label for memory-derived claims."""

    CONFIDENT = "confident"
    UNCERTAIN = "uncertain"
    CONTRADICTED = "contradicted"


def normalize_archive_publication_status(
    value: str | ArchivePublicationStatus | None,
) -> ArchivePublicationStatus | None:
    """Normalize raw archive publication status input.

    Returns ``None`` when the value is missing or unknown.
    """
    if value is None:
        return None
    if isinstance(value, ArchivePublicationStatus):
        return value
    try:
        return ArchivePublicationStatus(str(value).strip().lower())
    except ValueError:
        return None


def archive_publication_status_for_state(
    state: PublicationState,
) -> ArchivePublicationStatus:
    """Map canonical publication lifecycle to archive publication status."""
    if state == PublicationState.PUBLISHED:
        return ArchivePublicationStatus.PUBLIC
    if state == PublicationState.RESTRICTED:
        return ArchivePublicationStatus.RESTRICTED
    if state == PublicationState.ARCHIVED:
        return ArchivePublicationStatus.ARCHIVED
    return ArchivePublicationStatus.UNPUBLISHED


def publication_state_for_archive_status(
    status: ArchivePublicationStatus,
) -> PublicationState:
    """Map archive publication status back to canonical publication lifecycle."""
    if status == ArchivePublicationStatus.PUBLIC:
        return PublicationState.PUBLISHED
    if status == ArchivePublicationStatus.RESTRICTED:
        return PublicationState.RESTRICTED
    if status == ArchivePublicationStatus.ARCHIVED:
        return PublicationState.ARCHIVED
    return PublicationState.DRAFT


_PUBLIC_REVIEW_STATUSES: frozenset[str] = frozenset(
    {
        "verified_court_record",
        "official_police_open_data_report",
        "official_statistics_aggregate",
        "corrected",
    }
)

_PENDING_REVIEW_STATUSES: frozenset[str] = frozenset({"pending_review"})

_RESTRICTED_REVIEW_STATUSES: frozenset[str] = frozenset(
    {
        "news_only_context",
        "disputed",
        "rejected",
        "removed_from_public",
    }
)


def publication_state_for_review_status(
    review_status: str | None,
    is_public: bool,
) -> PublicationState:
    """Map legacy review/public fields to the canonical publication state."""
    if review_status in _PENDING_REVIEW_STATUSES:
        return PublicationState.PENDING_REVIEW

    if review_status in _PUBLIC_REVIEW_STATUSES:
        if is_public:
            return PublicationState.PUBLISHED
        return PublicationState.APPROVED

    if review_status in _RESTRICTED_REVIEW_STATUSES:
        return PublicationState.RESTRICTED

    return PublicationState.DRAFT
