from datetime import date

from sqlalchemy.orm import Session

from app.models.entities import Event, LegalSource, Outcome
from app.services.constants import ALLOWED_OUTCOME_TYPES


def create_verified_outcome(
    db: Session,
    event: Event,
    outcome_type: str,
    summary: str,
    source: LegalSource,
    outcome_date: date | None = None,
) -> Outcome:
    if outcome_type not in ALLOWED_OUTCOME_TYPES:
        raise ValueError(f"Unsupported outcome type: {outcome_type}")
    if not source.verified_flag or source.source_type not in {"court_record", "court_order", "appeal_decision", "official_statement"}:
        raise ValueError("Outcomes require a verified court, appeal, or official source.")

    outcome = Outcome(
        event_id=event.id,
        outcome_type=outcome_type,
        outcome_date=outcome_date,
        summary=summary,
        verified_source_id=source.id,
    )
    db.add(outcome)
    db.flush()
    return outcome

