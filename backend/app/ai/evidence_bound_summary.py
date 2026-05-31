"""Evidence-bound AI summary: only summarize content with a known evidence_id."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class EvidenceBoundSummary:
    evidence_id: int  # source_snapshot_id or review_item_id
    evidence_type: str  # "SourceSnapshot" | "ReviewItem"
    summary_text: str
    unsupported_claims: list[str]  # claims AI could not attribute to evidence
    reviewer_advisory: str = "This summary is for reviewer use only. Not for public display."


def summarize_with_evidence(
    evidence_id: int,
    evidence_type: str,
    raw_text: str,
    *,
    max_length: int = 500,
) -> EvidenceBoundSummary:
    """Produce a bounded summary attributed to *evidence_id*.

    In a real deployment this would call an LLM with structured output.
    This implementation truncates raw_text and flags no unsupported claims
    as a safe placeholder.
    """
    truncated = raw_text[:max_length].strip()
    if len(raw_text) > max_length:
        truncated += " [truncated]"

    return EvidenceBoundSummary(
        evidence_id=evidence_id,
        evidence_type=evidence_type,
        summary_text=truncated,
        unsupported_claims=[],
    )
