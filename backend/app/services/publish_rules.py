"""Auto-publish classification service.

Every inbound record is classified into one of three tiers:

* AUTO_PUBLISH  – safe to make immediately public (no review required)
* HOLD          – import the record but keep it in pending_review
* BLOCK         – reject the record outright; do not persist

Classification is determined by source_tier (a string constant defined below)
and optional heuristic checks on the record fields.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from app.policies.publication_policy import (
    PUBLIC_REVIEW_STATUSES,
    UNSAFE_MAP_PRECISIONS,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models.entities import SourceRegistry

# ---------------------------------------------------------------------------
# Source tier constants
# ---------------------------------------------------------------------------

# Tier A – auto-publish safe
TIER_AUTO = "auto"

# Tier B – import but hold for human review
TIER_HOLD = "hold"

# Tier C – block / never store
TIER_BLOCK = "block"

# Valid source tiers for public visibility per product requirements
VALID_SOURCE_TIERS = {
    "court_record",
    "official_police_open_data",
    "official_government_statistics",
    "verified_news_context",
}

# Location precision levels that block publication (private addresses)
BLOCKED_PRECISION_LEVELS = {
    "exact_private_address",
    "exact_residence",
    "home_address",
    "exact_address",
    "private_residence",
}

# Review/public status constants are re-exported from
# app.policies.publication_policy.  Keep this module as a compatibility layer
# for older imports; do not add competing status lists here.

# Mapping: source_name → default tier
_SOURCE_TIER_MAP: dict[str, str] = {
    # Natural Earth / GeoNames / court registry (static reference data)
    "natural_earth": TIER_AUTO,
    "geonames": TIER_AUTO,
    "court_location_registry": TIER_AUTO,
    # Statistics Canada aggregate (no individual records)
    "statistics_canada": TIER_AUTO,
    # FBI aggregate (agency-level counts)
    "fbi_crime_data": TIER_AUTO,
    # Official structured local police/city open-data feeds
    "chicago_data_portal": TIER_AUTO,
    "toronto_police": TIER_AUTO,
    # Saskatoon is the initial Canadian feed; hold for manual review until the
    # pipeline is validated and auto_publish_enabled is set in SourceRegistry.
    "saskatoon_police": TIER_HOLD,
    "los_angeles_open_data": TIER_AUTO,
    # CourtListener – hold because records include names and docket text
    "courtlistener": TIER_HOLD,
    "court_opinion_rss": TIER_HOLD,
    # GDELT news links – context only, never auto-publish
    "gdelt": TIER_HOLD,
    "media_cloud": TIER_HOLD,
    "news": TIER_HOLD,
    # Anything unknown defaults to HOLD
}

# Tiers that allow auto-publish when SourceRegistry explicitly grants it
_TRUSTED_OFFICIAL_TIERS: frozenset[str] = frozenset(
    {
        "court_record",
        "official_police_open_data",
        "official_government_statistics",
    }
)

# Tiers that are never auto-publishable regardless of registry settings
_NEVER_AUTO_TIERS: frozenset[str] = frozenset(
    {
        "news_only_context",
        "news_rss",
        "scraped_media",
        "social_media",
    }
)

# ---------------------------------------------------------------------------
# Numeric trust-tier weights (Phase B: source trust hierarchy)
# ---------------------------------------------------------------------------
# Higher value = more authoritative.  Used by conflict_resolution.py to decide
# whether an incoming write should be suppressed in favour of the existing value.

TRUST_TIER_PRIMARY_OFFICIAL: int = 5  # court_record, official_government_statistics
TRUST_TIER_POLICE_OPEN_DATA: int = 4  # official_police_open_data
TRUST_TIER_VERIFIED_NEWS: int = 3  # verified_news_context
TRUST_TIER_AGGREGATED_MEDIA: int = 2  # news_rss, news_only_context, media_cloud
TRUST_TIER_UNVERIFIED: int = 1  # scraped_media, social_media, unknown / default

_NUMERIC_TIER_MAP: dict[str, int] = {
    "court_record": TRUST_TIER_PRIMARY_OFFICIAL,
    "official_government_statistics": TRUST_TIER_PRIMARY_OFFICIAL,
    "official_police_open_data": TRUST_TIER_POLICE_OPEN_DATA,
    "verified_news_context": TRUST_TIER_VERIFIED_NEWS,
    "news_rss": TRUST_TIER_AGGREGATED_MEDIA,
    "news_only_context": TRUST_TIER_AGGREGATED_MEDIA,
    "media_cloud": TRUST_TIER_AGGREGATED_MEDIA,
    "scraped_media": TRUST_TIER_UNVERIFIED,
    "social_media": TRUST_TIER_UNVERIFIED,
}


def numeric_trust_tier(source_tier_str: str) -> int:
    """Return the integer trust-tier weight for a *source_tier* string value.

    Returns ``TRUST_TIER_UNVERIFIED`` (1) as a safe default for unknown tiers.
    """
    return _NUMERIC_TIER_MAP.get(source_tier_str, TRUST_TIER_UNVERIFIED)


def compute_reliability_score(source: "SourceRegistry") -> float:
    """Return a 0.0–1.0 reliability score: (tier_weight / max_weight) × health_score.

    Examples:
    - court_record  source at full health (1.0) → 1.0
    - unverified    source at full health (1.0) → 0.2  (1/5)
    - any source at zero health              → 0.0

    The health_score is clamped to [0.0, 1.0] before multiplication so
    out-of-range DB values cannot produce a result outside [0.0, 1.0].
    """
    tier_num = _NUMERIC_TIER_MAP.get(source.source_tier, TRUST_TIER_UNVERIFIED)
    weight = tier_num / TRUST_TIER_PRIMARY_OFFICIAL  # normalise to (0.0, 1.0]
    return round(weight * max(0.0, min(1.0, source.health_score)), 4)


# ---------------------------------------------------------------------------
# Heuristic patterns that force a record to BLOCK regardless of source tier
# ---------------------------------------------------------------------------

_BLOCK_PATTERNS: list[re.Pattern[str]] = [
    # Exact private addresses
    re.compile(
        r"\b\d{1,5}\s+\w[\w\s]{2,30}"
        r"\s+(st|street|ave|avenue|blvd|boulevard|rd|road|dr|drive|ln|lane|ct|court|pl|place|way)\b",
        re.IGNORECASE,
    ),
    # Social Security / SIN numbers
    re.compile(r"\b\d{3}[-\s]\d{2}[-\s]\d{4}\b"),
    # Explicit causal judge-to-crime language
    re.compile(
        r"\b(judge|justice)\s+\w+\s+(caused|committed|responsible for|guilty of)\b",
        re.IGNORECASE,
    ),
    # Social media post markers
    re.compile(
        r"\b(tweet|retweet|facebook post|instagram post|tiktok)\b", re.IGNORECASE
    ),
    # Defendant / offender names in title-case  (heuristic: "Name Surname" preceded by role word)
    re.compile(
        r"\b(defendant|offender|suspect|accused|arrestee)\s+[A-Z][a-z]+\s+[A-Z][a-z]+\b",
        re.IGNORECASE,
    ),
    # Scraped news accusations
    re.compile(
        r"\b(allegedly|accused of|charged with)\b.{0,80}\b(judge|justice)\b",
        re.IGNORECASE,
    ),
]

# Fields to inspect for block patterns
_TEXT_FIELDS = (
    "notes",
    "docket_text",
    "entry_description",
    "title",
    "summary",
    "caption",
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def source_tier(source_name: str, registry: SourceRegistry | None = None) -> str:
    """Return the publish tier for a given source name.

    If a SourceRegistry row is supplied it takes precedence over the static map:
    - Sources in _NEVER_AUTO_TIERS are always held for review.
    - Active sources with auto_publish_enabled, a trusted tier, and no
      requires_manual_review flag → TIER_AUTO.
    """
    if registry is not None:
        reg_tier = registry.source_tier
        if reg_tier in _NEVER_AUTO_TIERS:
            return TIER_HOLD
        if (
            registry.is_active
            and registry.auto_publish_enabled
            and not registry.requires_manual_review
            and reg_tier in _TRUSTED_OFFICIAL_TIERS
        ):
            return TIER_AUTO
    return _SOURCE_TIER_MAP.get(source_name, TIER_HOLD)


def classify_record(src_name: str, record: Any) -> str:
    """Classify a record and return TIER_AUTO, TIER_HOLD, or TIER_BLOCK.

    Args:
        src_name: The ingestion source name (must match _SOURCE_TIER_MAP keys).
        record:   Any object or dict with optional text fields.

    Returns:
        One of the TIER_* constants.
    """
    # 1. Block-patterns take highest priority regardless of source
    text_blob = _extract_text(record)
    if text_blob and _matches_block_pattern(text_blob):
        return TIER_BLOCK

    # 2. Source tier determines the base classification
    tier = source_tier(src_name)

    # 3. Additional field-level checks that bump TIER_AUTO → TIER_HOLD
    if tier == TIER_AUTO:
        if _has_person_name_fields(record):
            return TIER_HOLD
        if _has_exact_precision(record):
            return TIER_HOLD

    return tier


def review_status_for_tier(tier: str) -> str:
    """Return the review_status string to set based on publish tier."""
    if tier == TIER_AUTO:
        return "official_police_open_data_report"
    return "pending_review"


def public_visibility_for_tier(tier: str) -> bool:
    """Return the public_visibility bool to set based on publish tier."""
    return tier == TIER_AUTO


def is_publishable(record: Any) -> tuple[bool, list[str]]:
    """Check if a record passes pre-ingestion tier classification gates.

    .. deprecated::
        This helper is for **ingestion-time** tier classification only.
        It must NOT be called from display routes, serializers, or API
        responses that gate public access.  For display/publication
        decisions use :func:`app.policies.publication_policy.can_show_public_entity`
        or :func:`app.policies.publication_policy.can_publish_entity` instead.
        Those functions are the canonical source of truth for publication.

    A record passes if:
    - review_status is in PUBLIC_REVIEW_STATUSES
    - source_url exists
    - source_tier is one of VALID_SOURCE_TIERS
    - location_precision is not in BLOCKED_PRECISION_LEVELS
    - public_visibility is true
    - record has no unresolved safety flags

    Args:
        record: Any object or dict with required fields.

    Returns:
        Tuple of (is_publishable, list_of_blocking_reasons).
        If is_publishable is False, reasons explains why.
    """
    reasons: list[str] = []

    # Helper to safely get fields from dict or object
    def get_field(field_name: str) -> Any:
        if isinstance(record, dict):
            return record.get(field_name)
        return getattr(record, field_name, None)

    # 1. Check source URL exists
    source_url = get_field("source_url")
    if not source_url or (isinstance(source_url, str) and not source_url.strip()):
        reasons.append("missing_source_url")

    # 2. Check source tier is valid for public visibility
    # Try both source_tier and source_quality field names
    source_tier = get_field("source_tier") or get_field("source_quality")
    if not source_tier or source_tier not in VALID_SOURCE_TIERS:
        reasons.append(f"invalid_source_tier: {source_tier}")

    # 3. Check location precision is not a private address
    precision = get_field("precision_level")
    if precision and precision in BLOCKED_PRECISION_LEVELS:
        reasons.append(f"blocked_precision: {precision}")

    # 4. Check review status allows public visibility
    review_status = get_field("review_status")
    if not review_status or review_status not in PUBLIC_REVIEW_STATUSES:
        reasons.append(f"unapproved_status: {review_status}")

    # 5. Check public_visibility flag is true
    public_visibility = get_field("public_visibility") or get_field("is_public")
    if not public_visibility:
        reasons.append("public_visibility_false")

    # 6. Check for unresolved safety flags
    safety_flags = get_field("safety_flags") or []
    if (
        safety_flags
        and isinstance(safety_flags, (list, tuple))
        and len(safety_flags) > 0
    ):
        unresolved = [
            f
            for f in safety_flags
            if isinstance(f, dict) and f.get("resolved") is not True
        ]
        if unresolved:
            reasons.append(f"unresolved_safety_flags: {len(unresolved)}")

    # 7. Check for inferred judge/crime linkage without source support
    linkage_status = get_field("judge_crime_linkage_status")
    if linkage_status and linkage_status == "inferred_unsupported":
        reasons.append("unsupported_judge_crime_linkage")

    return (len(reasons) == 0, reasons)


def check_publication_safety(record: Any) -> dict:
    """Run full publication safety check and return detailed report.

    .. deprecated::
        Wraps :func:`is_publishable` which is for ingestion-time tier
        classification only.  For API responses that gate public display
        use :func:`app.policies.publication_policy.can_show_public_entity`.

    This is a more verbose version of is_publishable() that returns
    a full report suitable for logging during ingestion.
    """
    is_ok, reasons = is_publishable(record)

    def get_field(field_name: str) -> Any:
        if isinstance(record, dict):
            return record.get(field_name)
        return getattr(record, field_name, None)

    source_tier = get_field("source_tier") or get_field("source_quality")
    review_status = get_field("review_status")
    precision = get_field("precision_level")

    return {
        "safe_to_publish": is_ok,
        "can_be_public": is_ok,
        "blocking_reasons": reasons,
        "checks": {
            "has_source_url": bool(get_field("source_url")),
            "valid_source_tier": (
                source_tier in VALID_SOURCE_TIERS if source_tier else False
            ),
            "source_tier_value": source_tier,
            "safe_precision": (
                precision not in BLOCKED_PRECISION_LEVELS if precision else True
            ),
            "precision_value": precision,
            "approved_status": (
                review_status in PUBLIC_REVIEW_STATUSES if review_status else False
            ),
            "review_status_value": review_status,
            "public_visibility_enabled": bool(
                get_field("public_visibility") or get_field("is_public")
            ),
        },
        "warnings": [],
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_text(record: Any) -> str:
    """Concatenate all text-like fields from a record object or dict."""
    parts: list[str] = []
    for field in _TEXT_FIELDS:
        value = (
            record.get(field)
            if isinstance(record, dict)
            else getattr(record, field, None)
        )
        if value and isinstance(value, str):
            parts.append(value)
    return " ".join(parts)


def _matches_block_pattern(text: str) -> bool:
    return any(pat.search(text) for pat in _BLOCK_PATTERNS)


def _has_person_name_fields(record: Any) -> bool:
    """Return True if the record carries individual person-name data."""
    name_fields = ("judge_name", "defendant_name", "party_name", "assigned_to_str")
    for field in name_fields:
        value = (
            record.get(field)
            if isinstance(record, dict)
            else getattr(record, field, None)
        )
        if value and isinstance(value, str) and value.strip():
            return True
    # CourtListener ParsedRecord carries parties list
    parties = (
        record.get("parties")
        if isinstance(record, dict)
        else getattr(record, "parties", None)
    )
    if parties:
        return True
    return False


def _has_exact_precision(record: Any) -> bool:
    """Return True if the record precision level indicates an exact address."""
    precision = (
        record.get("precision_level")
        if isinstance(record, dict)
        else getattr(record, "precision_level", None)
    )
    if precision and isinstance(precision, str):
        return "exact" in precision.lower() or "address" in precision.lower()
    return False


# ---------------------------------------------------------------------------
# Registry-aware publish policy
# ---------------------------------------------------------------------------


def resolve_publication_policy(
    db: "Session",
    source_key: str,
    source_name: str,
) -> str:
    """Return the effective publish tier for a source.

    SourceRegistry is the authoritative gate.  The static ``_SOURCE_TIER_MAP``
    acts as a fallback *only* when the registry explicitly allows it.

    Rules (in order):
    1. Registry row not found  → TIER_HOLD  (fail closed)
    2. Registry ``is_active`` is False → TIER_HOLD
    3. Registry ``requires_manual_review`` is True → TIER_HOLD
    4. Registry ``auto_publish_enabled`` is False → TIER_HOLD
    5. Registry permits → delegate to static ``source_tier()`` for final tier

    The registry can only *restrict* (hold), never *promote* a TIER_HOLD/TIER_BLOCK
    source to TIER_AUTO.
    """
    from app.models.entities import SourceRegistry  # local import to avoid circular

    registry: SourceRegistry | None = (
        db.query(SourceRegistry).filter_by(source_key=source_key).first()
    )
    if registry is None and source_key != source_name:
        # Fallback: try matching by source_name used as key
        registry = db.query(SourceRegistry).filter_by(source_key=source_name).first()
    if registry is None:
        # Final fallback: match by the registry's own source_name field
        registry = db.query(SourceRegistry).filter_by(source_name=source_name).first()

    if registry is None:
        return TIER_HOLD  # Fail closed – unknown source

    if not registry.is_active:
        return TIER_HOLD

    if registry.requires_manual_review or not registry.auto_publish_enabled:
        return TIER_HOLD

    # Registry permits auto-publish; use static tier as final determinant.
    return source_tier(source_name, registry=registry)
