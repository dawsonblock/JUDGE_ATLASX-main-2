from dataclasses import dataclass

from app.services.constants import REPEAT_OFFENDER_INDICATORS
from app.services.text import normalize_text

LEGAL_RULES = [
    ("release_decision", ["released on conditions", "release on conditions", "release granted", "ordered released", "bond set"]),
    ("bail_decision", ["bail", "bond hearing", "detention hearing"]),
    ("sentencing", ["sentenced to", "judgment as to", "sentence imposed"]),
    ("revocation", ["supervised release revoked", "revocation", "violation of supervised release"]),
    ("appeal_decision", ["affirmed", "reversed", "vacated", "remanded", "appeal"]),
    ("court_order", ["order", "court ordered", "motion granted", "motion denied"]),
]

CRIME_RULES = [
    ("violent", ["assault", "homicide", "robbery", "shooting", "stabbing"]),
    ("property", ["burglary", "theft", "stolen", "arson", "mischief", "fraud"]),
    ("weapons", ["weapon", "firearm", "gun", "knife"]),
    ("drugs", ["drug", "narcotic", "controlled substance", "trafficking"]),
    ("public_order", ["disorder", "disturbance", "trespass", "public order"]),
    ("traffic", ["traffic", "dui", "impaired driving", "collision"]),
]


@dataclass(frozen=True)
class AILegalClassification:
    event_type: str
    confidence: float
    matched_keywords: list[str]
    repeat_offender_indicator: bool
    repeat_offender_indicators: list[str]


@dataclass(frozen=True)
class AICrimeClassification:
    incident_category: str
    confidence: float
    matched_keywords: list[str]


def classify_legal_record(text: str) -> AILegalClassification:
    normalized = normalize_text(text)
    matches: list[tuple[str, str]] = []
    for event_type, keywords in LEGAL_RULES:
        for keyword in keywords:
            if keyword in normalized:
                matches.append((event_type, keyword))
    repeat_indicators = [phrase for phrase in REPEAT_OFFENDER_INDICATORS + ["breach history", "repeat offending"] if phrase in normalized]
    return AILegalClassification(
        event_type=matches[0][0] if matches else "unknown",
        confidence=0.86 if matches else 0.2,
        matched_keywords=[match[1] for match in matches],
        repeat_offender_indicator=bool(repeat_indicators),
        repeat_offender_indicators=repeat_indicators,
    )


def classify_crime_record(text: str) -> AICrimeClassification:
    normalized = normalize_text(text)
    matches: list[tuple[str, str]] = []
    for category, keywords in CRIME_RULES:
        for keyword in keywords:
            if keyword in normalized:
                matches.append((category, keyword))
    return AICrimeClassification(
        incident_category=matches[0][0] if matches else "other",
        confidence=0.8 if matches else 0.25,
        matched_keywords=[match[1] for match in matches],
    )
