from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ExtractedClaim:
    text: str
    claim_type: str = "unclassified"
    confidence: float = 0.0
    evidence_required: bool = True
    authority: str = "derivative_only"


def extract_claims_from_text(text: str) -> list[dict[str, Any]]:
    cleaned = (text or "").strip()
    if not cleaned:
        return []

    normalized = cleaned.replace("\n", " ")
    sentences = [
        part.strip()
        for part in normalized.replace("?", ".").replace("!", ".").split(".")
        if part.strip()
    ]

    return [
        {
            "text": sentence,
            "claim_type": "explicit_text_span",
            "confidence": 0.25,
            "evidence_required": True,
            "authority": "derivative_only",
        }
        for sentence in sentences
    ]