"""Deterministic machine review engine for inbound records.

Every record passes through ``auto_review()`` before being written to the DB.
Returns a single ``AutoReviewResult`` that consolidates publish-rules tier
classification, SourceRegistry policy, evidence-linkage confidence, and
privacy guards into one decision.

Actions:
    publish       – TIER_AUTO record that passes all gates; set public immediately.
    quarantine    – Valid record but not safe to publish yet; store hidden.
    context_only  – News/scraped record; visible as context, never as primary data.
    block         – Reject outright; do not persist.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.services.publish_rules import (
    TIER_AUTO,
    TIER_BLOCK,
    TIER_HOLD,
    classify_record,
    source_tier as default_source_tier,
)

# Source names that are always context-only regardless of tier
_CONTEXT_ONLY_SOURCES: frozenset[str] = frozenset(
    {"gdelt", "media_cloud", "news", "court_opinion_rss"}
)

# Minimum confidence threshold to qualify for direct publish
_PUBLISH_CONFIDENCE_THRESHOLD = 0.70

# Sources that produce static reference data and never require snapshot hashes
_STATIC_REF_SOURCES: frozenset[str] = frozenset(
    {
        "natural_earth",
        "geonames",
        "court_location_registry",
        "statistics_canada",
        "fbi_crime_data",
    }
)

# Causation language: links a judge directly to causing a crime — hard block
_CAUSATION_RE = re.compile(
    r"\b(judge|ruled?|sentenced?|convicted?)\s+(caused?|responsible)\b",
    re.IGNORECASE,
)


@dataclass
class AutoReviewResult:
    """Result of deterministic machine review for a single record."""

    action: str
    """One of: 'publish', 'quarantine', 'context_only', 'block'."""

    review_status: str
    """Value to write to the incident/record review_status column."""

    public_visibility: bool
    """Value to write to is_public / public_visibility."""

    confidence: float
    """Confidence score in [0.0, 1.0] used for audit trails."""

    reasons: list[str] = field(default_factory=list)
    """Machine-readable codes explaining blocking or hold decisions."""

    warnings: list[str] = field(default_factory=list)
    """Non-blocking notes for operators (e.g. missing optional fields)."""


def auto_review(
    record: Any,
    source_name: str,
    *,
    has_snapshot_hash: bool = False,
    official_identifier: str | None = None,
    db_tier: str | None = None,
) -> AutoReviewResult:
    """Run deterministic machine review on a single inbound record.

    Args:
        record:             Any dict or dataclass/object with recognised fields.
        source_name:        Ingestion source name (matches SourceRegistry.source_key
                            and publish_rules._SOURCE_TIER_MAP).
        has_snapshot_hash:  True when a SHA-256 evidence snapshot was successfully
                            written to the EvidenceStore.
        official_identifier: Court docket, police file number, or other
                            authoritative identifier from the source.
        db_tier:            Tier returned by ``resolve_publication_policy()`` for
                            this source (pre-fetched by caller so we stay DB-free).
                            If None, falls back to static ``_SOURCE_TIER_MAP``.

    Returns:
        AutoReviewResult with final action + DB field values.
    """
    reasons: list[str] = []
    warnings: list[str] = []
    confidence = 1.0

    # ------------------------------------------------------------------
    # Gate 0a: Missing source URL → cannot establish provenance (quarantine)
    # ------------------------------------------------------------------
    source_url = _get_field(record, "source_url")
    if not source_url or (isinstance(source_url, str) and not source_url.strip()):
        return AutoReviewResult(
            action="quarantine",
            review_status="pending_review",
            public_visibility=False,
            confidence=0.0,
            reasons=["missing_source_url"],
        )

    # ------------------------------------------------------------------
    # Gate 0b: Non-reference source with no snapshot hash → evidence gap
    # ------------------------------------------------------------------
    if source_name not in _STATIC_REF_SOURCES and not has_snapshot_hash:
        return AutoReviewResult(
            action="quarantine",
            review_status="pending_review",
            public_visibility=False,
            confidence=0.0,
            reasons=["no_snapshot_hash"],
        )

    # ------------------------------------------------------------------
    # Gate 0c: Causation language linking judge to crime — hard block
    # ------------------------------------------------------------------
    _text_blob_0c = " ".join(
        str(_get_field(record, fld) or "")
        for fld in (
            "notes",
            "docket_text",
            "entry_description",
            "title",
            "summary",
            "caption",
            "description",
        )
    )
    if _CAUSATION_RE.search(_text_blob_0c):
        return AutoReviewResult(
            action="block",
            review_status="rejected",
            public_visibility=False,
            confidence=1.0,
            reasons=["causation_language_detected"],
        )

    # ------------------------------------------------------------------
    # Gate 1: Block pattern check (highest priority, unconditional)
    # ------------------------------------------------------------------
    record_tier = classify_record(source_name, record)
    if record_tier == TIER_BLOCK:
        return AutoReviewResult(
            action="block",
            review_status="rejected",
            public_visibility=False,
            confidence=1.0,
            reasons=["block_pattern_matched"],
        )

    # ------------------------------------------------------------------
    # Gate 2: Scraped / news sources → always context_only
    # ------------------------------------------------------------------
    if source_name in _CONTEXT_ONLY_SOURCES:
        return AutoReviewResult(
            action="context_only",
            review_status="news_only_context",
            public_visibility=False,
            confidence=0.5,
            reasons=["scraped_source_context_only"],
        )

    # ------------------------------------------------------------------
    # Gate 3: Effective tier (DB registry overrides static map)
    # ------------------------------------------------------------------
    effective_tier = (
        db_tier if db_tier is not None else default_source_tier(source_name)
    )

    if effective_tier == TIER_HOLD or record_tier == TIER_HOLD:
        reasons.append("source_requires_review")
        confidence -= 0.30

    # ------------------------------------------------------------------
    # Gate 4: Evidence snapshot linkage
    # ------------------------------------------------------------------
    if has_snapshot_hash:
        confidence = min(confidence + 0.10, 1.0)
    else:
        reasons.append("no_snapshot_hash")
        confidence -= 0.15

    # ------------------------------------------------------------------
    # Gate 5: Official identifier
    # ------------------------------------------------------------------
    if official_identifier and official_identifier.strip():
        confidence = min(confidence + 0.05, 1.0)
    else:
        warnings.append("no_official_identifier")

    # ------------------------------------------------------------------
    # Gate 6: Coordinate completeness
    # ------------------------------------------------------------------
    lat = _get_field(record, "latitude_public")
    lon = _get_field(record, "longitude_public")
    if lat is None or lon is None:
        reasons.append("missing_coordinates")
        confidence -= 0.30
    elif float(lat) == 0.0 or float(lon) == 0.0:
        reasons.append("zero_coordinates")
        confidence -= 0.30

    # ------------------------------------------------------------------
    # Gate 7: Precision level — exact/private addresses always blocked
    # ------------------------------------------------------------------
    precision = _get_field(record, "precision_level")
    if precision and isinstance(precision, str):
        p = precision.lower()
        if "exact" in p or "address" in p or "residence" in p:
            reasons.append(f"blocked_precision:{precision}")
            return AutoReviewResult(
                action="block",
                review_status="rejected",
                public_visibility=False,
                confidence=1.0,
                reasons=reasons,
                warnings=warnings,
            )

    # ------------------------------------------------------------------
    # Final decision
    # ------------------------------------------------------------------
    confidence = max(0.0, min(1.0, confidence))

    if (
        effective_tier == TIER_AUTO
        and record_tier == TIER_AUTO
        and confidence >= _PUBLISH_CONFIDENCE_THRESHOLD
    ):
        return AutoReviewResult(
            action="review_ready",
            review_status="pending_review",
            public_visibility=False,
            confidence=confidence,
            reasons=reasons,
            warnings=warnings,
        )

    return AutoReviewResult(
        action="quarantine",
        review_status="pending_review",
        public_visibility=False,
        confidence=confidence,
        reasons=reasons,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_field(record: Any, field_name: str) -> Any:
    """Safely get a named field from a dict or dataclass/object."""
    if isinstance(record, dict):
        return record.get(field_name)
    return getattr(record, field_name, None)
