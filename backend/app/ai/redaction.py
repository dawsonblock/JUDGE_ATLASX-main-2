import re

from app.ai.schemas import RedactionResult

ADDRESS_PATTERN = re.compile(
    r"\b(?:home|residence|victim|suspect)?\s*(?:address|residence|home)\s*(?:is|:)?\s*\d{1,6}\s+[A-Za-z0-9 .'-]+\s+"
    r"(?:Street|St|Avenue|Ave|Road|Rd|Drive|Dr|Lane|Ln|Court|Ct|Boulevard|Blvd)\b",
    re.IGNORECASE,
)
DOB_PATTERN = re.compile(r"\b(?:dob|date of birth)\s*[:\-]?\s*(?:\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|[A-Z][a-z]+ \d{1,2}, \d{4})\b", re.IGNORECASE)
PHONE_PATTERN = re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)\d{3}[-.\s]?\d{4}\b")
EMAIL_PATTERN = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.IGNORECASE)
COORD_PATTERN = re.compile(r"\b(?:residential|home|residence)\s+coordinates?\s*[:\-]?\s*-?\d{1,3}\.\d+,\s*-?\d{1,3}\.\d+\b", re.IGNORECASE)

TERM_RISKS = {
    "minor_identity": re.compile(r"\b(?:minor|juvenile|child)\s+(?:named|identified as|is)\s+[A-Z][a-z]+", re.IGNORECASE),
    "family_details": re.compile(r"\b(?:spouse|wife|husband|child|daughter|son|parent|family member)\b", re.IGNORECASE),
    "medical_information": re.compile(r"\b(?:medical diagnosis|medical condition|medication|psychiatric|therapy|hospitalized)\b", re.IGNORECASE),
    "victim_address": re.compile(r"\bvictim(?:'s)?\s+(?:address|home|residence)\b", re.IGNORECASE),
    "suspect_address": re.compile(r"\bsuspect(?:'s)?\s+(?:address|home|residence)\b", re.IGNORECASE),
}


def redact_private_data(text: str, source_url: str | None, source_quality: str) -> RedactionResult:
    detected: list[str] = []
    redacted = text or ""

    replacements = [
        ("home_address", ADDRESS_PATTERN, "[REDACTED PRIVATE ADDRESS]"),
        ("dob", DOB_PATTERN, "[REDACTED DOB]"),
        ("phone", PHONE_PATTERN, "[REDACTED PHONE]"),
        ("email", EMAIL_PATTERN, "[REDACTED EMAIL]"),
        ("exact_residential_coordinates", COORD_PATTERN, "[REDACTED RESIDENTIAL COORDINATES]"),
    ]
    for label, pattern, replacement in replacements:
        if pattern.search(redacted):
            detected.append(label)
            redacted = pattern.sub(replacement, redacted)

    for label, pattern in TERM_RISKS.items():
        if pattern.search(text or ""):
            detected.append(label)

    privacy_risk = bool(detected)
    return RedactionResult(
        source_url=source_url,
        source_quality=source_quality,
        confidence=0.95 if privacy_risk else 0.8,
        source_quote=_quote(text),
        neutral_summary="Private or sensitive content detected and flagged for review." if privacy_risk else "No private data pattern detected by deterministic redaction.",
        privacy_risk=privacy_risk,
        publish_recommendation="block" if {"home_address", "victim_address", "suspect_address", "dob", "exact_residential_coordinates"} & set(detected) else ("review_required" if privacy_risk else "safe_auto_publish"),
        redacted_text=redacted,
        detected_risks=sorted(set(detected)),
    )


def _quote(text: str) -> str:
    compact = " ".join((text or "").split())
    return compact[:500]

