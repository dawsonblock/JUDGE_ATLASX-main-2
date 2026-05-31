"""Approved extraction classes and their associated prompts and confidence caps.

Only classes listed in ``APPROVED_CLASSES`` may be requested from the
LangExtract runner.  This table is the single source of truth for what the
system is permitted to extract.

**Confidence cap policy**
Each class carries a ``confidence_cap`` that limits the maximum confidence
score the runner will record.  Caps reflect the reliability of that type of
extraction at the structured-document tier vs. general news text.

Never raise a cap without a documented review; lower caps first if anomalies
are observed.
"""

from __future__ import annotations

from typing import TypedDict


class _ClassSpec(TypedDict):
    """Internal spec for one extraction class."""

    confidence_cap: float
    """Maximum confidence value permitted for this class (inclusive)."""

    description: str
    """Human-readable description of what this class extracts."""

    prompt_hint: str
    """Brief instruction injected into the LangExtract prompt header."""


# ---------------------------------------------------------------------------
# Approved extraction classes
# ---------------------------------------------------------------------------

APPROVED_CLASSES: dict[str, _ClassSpec] = {
    "person_name": {
        "confidence_cap": 0.60,
        "description": "Full name of a person mentioned in the source text.",
        "prompt_hint": (
            "Extract the full name of any person explicitly mentioned. "
            "Do not infer names from pronouns or partial references."
        ),
    },
    "location": {
        "confidence_cap": 0.65,
        "description": (
            "Specific geographic location (city, province, address, or region) "
            "mentioned in the source text."
        ),
        "prompt_hint": (
            "Extract named geographic locations only. "
            "Do not include vague references such as 'downtown' without a city."
        ),
    },
    "organization": {
        "confidence_cap": 0.60,
        "description": "Name of an organization, company, or government body.",
        "prompt_hint": (
            "Extract the full formal name of an organization. "
            "Include acronyms only when spelled out in the text."
        ),
    },
    "date": {
        "confidence_cap": 0.75,
        "description": "A specific date or date range mentioned in the source text.",
        "prompt_hint": (
            "Extract explicit date expressions only (e.g., 'March 5, 2024'). "
            "Do not infer dates from relative expressions like 'last week'."
        ),
    },
    "charge_type": {
        "confidence_cap": 0.55,
        "description": "A legal charge or offence type cited in the source text.",
        "prompt_hint": (
            "Extract the name of a specific criminal or civil charge type as "
            "stated verbatim. Do not paraphrase or normalise."
        ),
    },
}

# Convenience mapping: class_name → confidence_cap (avoids nested access).
CONFIDENCE_CAPS: dict[str, float] = {
    name: spec["confidence_cap"] for name, spec in APPROVED_CLASSES.items()
}

# Fallback cap applied when a class is approved but not in CONFIDENCE_CAPS.
# Should never be reached given CONFIDENCE_CAPS is derived from APPROVED_CLASSES.
DEFAULT_CONFIDENCE_CAP: float = 0.60
