"""Public-safety helpers for serializing court-event data.

Thin wrappers around the implementation in app.serializers.public so
callers can import from a single, spec-mandated module path.
"""

from app.models.entities import Case, Defendant, Event, LegalSource
from app.serializers.public import (
    _dedupe_pairs,
    _defendant_name_pairs,
    _looks_like_case_caption,
    _replace_known_defendant_names,
    sanitize_case_caption as _safe_caption,
    sanitize_public_text as _safe_text,
    sanitize_source_title as _safe_title,
)


def safe_case_caption(
    case: Case,
    event_defendants: list[Defendant] | None = None,
) -> str:
    """Return a public-safe case caption with defendant names replaced by DEF labels.

    Delegates to serializers.public.sanitize_case_caption.  If an event
    is not available, a synthetic name-pair list built from event_defendants
    is used so the caller can pass defendant objects directly.
    """
    if event_defendants is not None:
        pairs = _dedupe_pairs(
            [pair for d in event_defendants for pair in _defendant_name_pairs(d)]
        )
        caption = _replace_known_defendant_names(case.caption, pairs)
        if caption != (case.caption or ""):
            return _safe_text(caption, "Reviewed case record")
        if _looks_like_case_caption(caption):
            labels = [d.anonymized_id for d in event_defendants]
            if labels:
                return f"Reviewed case record ({', '.join(labels)})"
            return "Reviewed case record"
        return _safe_text(caption, "Reviewed case record")
    return _safe_caption(case, None)


def safe_source_title(
    source: LegalSource,
    linked_event: Event | None = None,
) -> str:
    """Return a public-safe source title with defendant names redacted.

    Delegates to serializers.public.sanitize_source_title.
    """
    return _safe_title(source, linked_event)


def safe_summary(
    text: str | None,
    defendants: list[Defendant] | None = None,
    fallback: str = "Reviewed public legal summary.",
) -> str:
    """Return a public-safe summary with defendant names, DOBs, phones,
    emails, addresses, and victim/suspect terms redacted.

    Delegates to serializers.public.sanitize_public_text after replacing
    any known defendant public names with their anonymized labels.
    """
    if defendants:
        pairs = _dedupe_pairs(
            [pair for d in defendants for pair in _defendant_name_pairs(d)]
        )
        text = _replace_known_defendant_names(text, pairs)
    return _safe_text(text, fallback)
