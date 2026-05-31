from app.ai.classify import classify_crime_record, classify_legal_record


def neutral_legal_summary(text: str, source_quote: str) -> str:
    classification = classify_legal_record(text)
    label = classification.event_type.replace("_", " ")
    summary = f"Source-backed legal record indicates a {label}. Source excerpt: \"{source_quote}\""
    if classification.repeat_offender_indicator:
        summary += " Repeat-offender indicator language appears in the source; this is an indicator, not proof."
    return summary


def neutral_crime_summary(text: str, source_quote: str) -> str:
    classification = classify_crime_record(text)
    return (
        f"Reported incident categorized as {classification.incident_category}. "
        f"Reported incident records are not proof of guilt or conviction. Source excerpt: \"{source_quote}\""
    )

