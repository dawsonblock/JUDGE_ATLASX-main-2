from dataclasses import dataclass

from app.services.constants import REPEAT_OFFENDER_INDICATORS
from app.services.text import normalize_text


KEYWORD_RULES: list[tuple[str, list[str]]] = [
    ("detention_order", ["order of detention", "detained pending trial"]),
    ("release_order", ["released on conditions", "bond set"]),
    ("bond_modification", ["bond modified", "modification of conditions"]),
    ("sentencing", ["judgment as to", "sentenced to"]),
    ("probation_order", ["probation ordered", "sentence of probation"]),
    ("supervised_release", ["supervised release imposed", "term of supervised release"]),
    ("revocation", ["supervised release revoked", "revocation of supervised release"]),
    ("resentencing", ["resentenced", "resentencing"]),
    ("appeal_reversal", ["reversed", "vacated and remanded"]),
    ("appeal_remand", ["remanded", "vacated and remanded"]),
    ("appeal_affirmance", ["affirmed"]),
    ("indictment", ["indictment", "indicted"]),
    ("dismissal", ["case dismissed", "dismissed"]),
    ("sentencing_recommendation", ["sentencing recommendation"]),
    ("motion_to_suppress", ["motion to suppress"]),
    ("mitigation_filing", ["mitigation", "sentencing memorandum"]),
    ("iac_finding", ["ineffective assistance of counsel", "strickland"]),
    ("judicial_misconduct_finding", ["judicial misconduct"]),
    ("ethics_report", ["ethics report"]),
    ("published_opinion", ["published opinion"]),
    ("unpublished_opinion", ["unpublished opinion"]),
    ("press_release", ["press release"]),
    ("news_coverage", ["news coverage"]),
]


@dataclass(frozen=True)
class Classification:
    event_type: str
    confidence: float
    matched_keywords: list[str]
    repeat_offender_indicator: bool
    repeat_offender_indicators: list[str]


def classify_event(text: str) -> Classification:
    normalized = normalize_text(text)
    matches: list[tuple[str, str]] = []
    for event_type, keywords in KEYWORD_RULES:
        for keyword in keywords:
            if keyword in normalized:
                matches.append((event_type, keyword))

    event_type = matches[0][0] if matches else "news_coverage"
    matched_keywords = [match[1] for match in matches]
    confidence = 0.9 if matched_keywords else 0.25
    repeat_indicators = [phrase for phrase in REPEAT_OFFENDER_INDICATORS if phrase in normalized]

    return Classification(
        event_type=event_type,
        confidence=confidence,
        matched_keywords=matched_keywords,
        repeat_offender_indicator=bool(repeat_indicators),
        repeat_offender_indicators=repeat_indicators,
    )
