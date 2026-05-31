"""Source-level bias analysis based on keyword indicators.

All rule-based — no LLM calls.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session

from app.services.text import normalize_text

# ---------------------------------------------------------------------------
# Bias indicator catalogue
# ---------------------------------------------------------------------------

BIAS_INDICATORS: dict[str, list[str]] = {
    "prosecutorial": [
        "dangerous offender",
        "career criminal",
        "violent history",
        "menace to society",
        "predatory",
        "calculated",
        "brutal crime",
        "depraved",
    ],
    "defense": [
        "wrongfully accused",
        "no prior record",
        "character witness",
        "community ties",
        "family man",
        "first-time offender",
        "minor role",
        "entrapment",
    ],
    "sensationalist": [
        "shocking",
        "horrific",
        "monster",
        "predator",
        "gruesome",
        "heinous",
        "chilling",
        "terrifying",
        "bombshell",
        "explosive",
    ],
    "rehabilitative": [
        "rehabilitation",
        "second chance",
        "turned his life",
        "turned her life",
        "reintegration",
        "redemption",
        "treatment program",
        "mentorship",
    ],
}

_MIN_INDICATORS: int = 1  # minimum matches to produce a report
_MAX_SCORE: float = 1.0


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class BiasReport:
    source_name: str
    bias_type: Optional[str]  # None if no bias detected
    confidence: float
    indicator_count: int
    matched_phrases: list[str]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _score_text(text: str) -> tuple[Optional[str], float, int, list[str]]:
    """Return (bias_type, confidence, indicator_count, matched_phrases)."""
    t = normalize_text(text)
    best_type: Optional[str] = None
    best_count = 0
    best_phrases: list[str] = []

    for bias_type, keywords in BIAS_INDICATORS.items():
        matched = [kw for kw in keywords if kw in t]
        if len(matched) > best_count:
            best_count = len(matched)
            best_type = bias_type
            best_phrases = matched

    if best_count < _MIN_INDICATORS:
        return None, 0.0, 0, []

    total_indicators = len(BIAS_INDICATORS.get(best_type or "", []))
    confidence = round(min(_MAX_SCORE, best_count / max(1, total_indicators) + 0.15), 4)
    return best_type, confidence, best_count, best_phrases


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def analyze_source_text(text: str, source_name: str) -> BiasReport:
    """Analyze a raw text excerpt for bias indicators.

    Works without a database — suitable for pipeline integration.
    """
    bias_type, confidence, count, phrases = _score_text(text)
    return BiasReport(
        source_name=source_name,
        bias_type=bias_type,
        confidence=confidence,
        indicator_count=count,
        matched_phrases=phrases,
    )


def get_source_bias_profile(db: Session, source_name: str) -> list[BiasReport]:
    """Aggregate bias analysis across all SourceSnapshot records for *source_name*."""
    from app.models.entities import SourceSnapshot  # local import to avoid circular

    snapshots = (
        db.query(SourceSnapshot).filter(SourceSnapshot.source_key == source_name).all()
    )

    reports: list[BiasReport] = []
    for snap in snapshots:
        text = getattr(snap, "raw_text", None) or getattr(snap, "content", None) or ""
        if not text:
            continue
        report = analyze_source_text(str(text), source_name)
        if report.indicator_count >= _MIN_INDICATORS:
            reports.append(report)
    return reports
