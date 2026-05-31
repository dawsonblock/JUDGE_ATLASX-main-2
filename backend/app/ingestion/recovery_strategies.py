"""Phase 4: Error Recovery Strategies & Retry Logic

Provides classification of ingestion errors as transient vs. permanent, and
implements exponential backoff retry logic for automatic recovery.

Transient errors (retriable):
- Network timeouts/connection resets
- HTTP 429 (rate limited), 503 (service unavailable), 502 (bad gateway)
- Database connection pool exhaustion
- Temporary resource unavailability

Permanent errors (non-retriable):
- Authentication failures (401, 403)
- Invalid source configuration
- Adapter contract violations
- Data validation errors (payload schema mismatch)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.models.entities import IngestionRun


class ErrorCategory(str, Enum):
    """Classification of error types for retry decision-making."""

    TRANSIENT = "transient"  # Retriable: network, temporary resource issues
    PERMANENT = "permanent"  # Non-retriable: config, auth, contract violations
    UNKNOWN = "unknown"  # Unclassified: log and quarantine


class RecoveryStrategy(str, Enum):
    """Strategy for recovering from a failed ingestion."""

    EXPONENTIAL_BACKOFF = "exponential_backoff"  # Auto-retry with backoff
    QUARANTINE_FOR_REVIEW = "quarantine_for_review"  # Admin intervention required
    SKIP_RETRY = "skip_retry"  # Don't retry, mark as permanent failure


@dataclass
class ErrorClassification:
    """Result of error classification for a failed ingestion."""

    category: ErrorCategory
    strategy: RecoveryStrategy
    reason: str
    retriable: bool
    suggested_backoff_seconds: int | None = None


# ── Error pattern matching ────────────────────────────────────────────────────

# Transient error patterns (from error messages or exception types)
_TRANSIENT_ERROR_PATTERNS = [
    # Network errors
    r"connection.*reset|connection refused|connection.*timeout",
    r"network.*unreachable|host.*unreachable",
    r"broken.*pipe|reset by peer",
    # HTTP 5xx errors
    r"http.*50[2-9]|http.*5\d{2}",  # 502, 503, 504, etc.
    r"http.*429",  # Rate limit
    # Database/Resource contention
    r"connection.*pool.*exhaust|pool.*timeout",
    r"too many connections|max connections|connection limit",
    r"resource.*temporary|temporary.*unavailable",
    # Request timeouts
    r"request.*timeout|socket.*timeout",
    r"operation timed out|deadline.*exceed",
]

_PERMANENT_ERROR_PATTERNS = [
    # Authentication
    r"401|unauthorized|authentication failed",
    r"403|forbidden|permission denied|access denied",
    # Configuration/Contract
    r"adapter.*contract.*violation|contract.*violation",
    r"schema.*mismatch|field.*required|validation.*error",
    r"parser.*version.*mismatch|incompatible.*parser",
    # Source configuration
    r"invalid.*config|missing.*config|malformed",
    r"no.*raw.*content|empty.*content|content.*missing",
    r"source.*disabled|source.*deprecated|source.*inactive",
]


def classify_error(error_message: str | None) -> ErrorClassification:
    """Classify an error as transient or permanent.

    Scans error_message against known patterns to determine if retry is
    appropriate. Falls back to UNKNOWN if no pattern matches.

    Args:
        error_message: Error string from ingestion failure (usually from
                      IngestionRun.errors list or last_error field)

    Returns:
        ErrorClassification with category, strategy, and suggested backoff
    """
    if not error_message:
        # No error information; default to quarantine for review
        return ErrorClassification(
            category=ErrorCategory.UNKNOWN,
            strategy=RecoveryStrategy.QUARANTINE_FOR_REVIEW,
            reason="No error message provided",
            retriable=False,
        )

    error_lower = error_message.lower()

    # Check transient patterns first (retry-friendly)
    for pattern in _TRANSIENT_ERROR_PATTERNS:
        if re.search(pattern, error_lower):
            return ErrorClassification(
                category=ErrorCategory.TRANSIENT,
                strategy=RecoveryStrategy.EXPONENTIAL_BACKOFF,
                reason=f"Transient error detected: {error_message[:100]}",
                retriable=True,
                suggested_backoff_seconds=60,  # Base backoff, will exponentially scale
            )

    # Check permanent patterns
    for pattern in _PERMANENT_ERROR_PATTERNS:
        if re.search(pattern, error_lower):
            return ErrorClassification(
                category=ErrorCategory.PERMANENT,
                strategy=RecoveryStrategy.QUARANTINE_FOR_REVIEW,
                reason=f"Permanent error detected: {error_message[:100]}",
                retriable=False,
            )

    # Unknown error: default to quarantine for review
    return ErrorClassification(
        category=ErrorCategory.UNKNOWN,
        strategy=RecoveryStrategy.QUARANTINE_FOR_REVIEW,
        reason=f"Unclassified error: {error_message[:100]}",
        retriable=False,
    )


# ── Exponential backoff calculation ───────────────────────────────────────────

def calculate_backoff_seconds(
    attempt: int,
    base_seconds: int = 60,
    max_seconds: int = 3600,
    jitter_factor: float = 0.1,
) -> int:
    """Calculate exponential backoff duration with jitter.

    Formula: min(base * 2^attempt + random(0, jitter%), max_seconds)

    Args:
        attempt: Retry attempt number (0-indexed; attempt 0 = first backoff)
        base_seconds: Base backoff duration (default 60)
        max_seconds: Maximum backoff duration cap (default 3600 = 1 hour)
        jitter_factor: Random jitter as fraction of backoff (default 0.1 = 10%)

    Returns:
        Backoff duration in seconds, capped at max_seconds (including jitter)
    """
    import random

    # Calculate exponential: base * 2^attempt
    exponential = base_seconds * (2 ** attempt)

    # Add jitter: random(0, jitter_factor * exponential)
    # Do this before capping to keep jitter proportional
    jitter = random.random() * (jitter_factor * exponential)
    with_jitter = exponential + jitter

    # Cap the final result at max_seconds
    return int(min(with_jitter, max_seconds))


def should_retry_ingestion(
    run: IngestionRun,
    max_retries: int = 3,
) -> tuple[bool, str]:
    """Determine if an ingestion should be retried.

    Checks error classification, retry count, and permanent failure markers.

    Args:
        run: Completed IngestionRun with failure details
        max_retries: Maximum number of retry attempts allowed

    Returns:
        (should_retry: bool, reason: str)
    """
    # Get the primary error message
    if not run.errors:
        return False, "No errors recorded; not retrying"

    error_msg = str(run.errors[0]) if isinstance(run.errors, list) else str(run.errors)

    # Classify the error
    classification = classify_error(error_msg)

    # Check retry attempt count
    retry_count = getattr(run, "retry_count", 0) or 0
    if retry_count >= max_retries:
        return False, f"Max retries ({max_retries}) exceeded"

    # Decision based on classification
    if classification.category == ErrorCategory.TRANSIENT:
        return True, f"Transient error (attempt {retry_count + 1}/{max_retries})"

    if classification.category == ErrorCategory.PERMANENT:
        return False, "Permanent error; cannot retry"

    # Unknown: don't retry automatically, quarantine for review
    return False, "Unknown error classification; quarantine for review"


# ── Health degradation monitoring ─────────────────────────────────────────────

def is_health_degraded(health_score: float, threshold: float = 0.6) -> bool:
    """Check if source health has degraded below acceptable threshold.

    Args:
        health_score: Current health_score from SourceRegistry (0.0-1.0)
        threshold: Degradation threshold (default 0.6 = 60%)

    Returns:
        True if health_score <= threshold
    """
    # Use 1.0 as default only if health_score is None, not if it's 0.0
    score = 1.0 if health_score is None else health_score
    return score <= threshold


def get_health_status_label(health_score: float) -> str:
    """Get human-readable health status from score.

    Args:
        health_score: Current health_score (0.0-1.0)

    Returns:
        Status label: "healthy", "degraded", "critical"
    """
    # Use 1.0 as default only if health_score is None, not if it's 0.0
    score = 1.0 if health_score is None else health_score
    if score >= 0.8:
        return "healthy"
    if score >= 0.6:
        return "degraded"
    return "critical"


# ── Transient error detection helpers ─────────────────────────────────────────

def is_timeout_error(error_message: str) -> bool:
    """Check if error is a timeout or connection timeout."""
    return bool(re.search(r"timeout|deadline.*exceed|timed out", error_message.lower()))


def is_rate_limit_error(error_message: str) -> bool:
    """Check if error is a rate limit (429) or quota error."""
    return bool(re.search(r"429|rate.*limit|quota.*exceed", error_message.lower()))


def is_service_unavailable_error(error_message: str) -> bool:
    """Check if error is a service unavailability (5xx)."""
    return bool(re.search(r"50[2-9]|service.*unavailable", error_message.lower()))


def is_connection_error(error_message: str) -> bool:
    """Check if error is a network/connection error."""
    return bool(
        re.search(
            r"connection.*reset|connection refused|network.*unreachable",
            error_message.lower(),
        )
    )
