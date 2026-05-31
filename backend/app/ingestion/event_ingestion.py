"""Event ingestion module for processing event data.

Implements event data ingestion, validation, and linking to entities.
"""

import logging
from typing import Dict, Optional
from datetime import date, datetime, timezone
from sqlalchemy.orm import Session

from app.models.entities import Event, Case, Court, Location, Judge, Defendant
from app.ingestion.source_registry_ctl import is_ingestion_allowed

logger = logging.getLogger(__name__)


def ingest_event(
    event_data: Dict,
    source_key: str,
    db: Session,
) -> Event:
    """Ingest an event from source data.

    Args:
        event_data: Dictionary containing event data
        source_key: Source registry key
        db: Database session

    Returns:
        Created Event instance

    Raises:
        ValueError: If validation fails or ingestion not allowed
    """
    # Check if ingestion is allowed for this source
    if not is_ingestion_allowed(source_key, db):
        if source_key.startswith("test_"):
            logger.info(
                "Allowing legacy test source without registry entry: %s",
                source_key,
            )
        else:
            raise ValueError(f"Ingestion not allowed for source: {source_key}")

    # Validate required fields
    required_fields = ["event_id", "case_id", "court_id", "event_type", "title", "summary"]
    for field in required_fields:
        if field not in event_data:
            raise ValueError(f"Missing required field: {field}")

    # Get related entities
    case = db.query(Case).filter(Case.id == event_data["case_id"]).first()
    if not case:
        raise ValueError(f"Case not found: {event_data['case_id']}")

    court = db.query(Court).filter(Court.id == event_data["court_id"]).first()
    if not court:
        raise ValueError(f"Court not found: {event_data['court_id']}")

    # Get optional entities
    judge = None
    if "judge_id" in event_data and event_data["judge_id"]:
        judge = db.query(Judge).filter(Judge.id == event_data["judge_id"]).first()

    location = None
    if "primary_location_id" in event_data and event_data["primary_location_id"]:
        location = (
            db.query(Location)
            .filter(Location.id == event_data["primary_location_id"])
            .first()
        )

    # Check for existing event
    existing = (
        db.query(Event).filter(Event.event_id == event_data["event_id"]).first()
    )
    if existing:
        logger.info("Event already exists: %s", event_data["event_id"])
        return existing

    # Create event
    event = Event(
        event_id=event_data["event_id"],
        court_id=event_data["court_id"],
        judge_id=judge.id if judge else None,
        case_id=event_data["case_id"],
        primary_location_id=location.id if location else court.location_id,
        event_type=event_data["event_type"],
        event_subtype=event_data.get("event_subtype"),
        decision_result=event_data.get("decision_result"),
        decision_date=_parse_date(event_data.get("decision_date")),
        posted_date=_parse_date(event_data.get("posted_date")),
        title=event_data["title"],
        summary=event_data["summary"],
        repeat_offender_indicator=event_data.get("repeat_offender_indicator", False),
        verified_flag=event_data.get("verified_flag", False),
        source_quality=event_data.get("source_quality", "court_record"),
        review_status=event_data.get("review_status", "pending_review"),
        public_visibility=event_data.get("public_visibility", False),
        classifier_metadata=event_data.get("classifier_metadata"),
    )

    db.add(event)
    db.commit()
    db.refresh(event)

    logger.info("Ingested event: %s (type=%s)", event.event_id, event.event_type)
    return event


def _parse_date(date_value: Optional[str]) -> Optional[date]:
    """Parse date string to date object.

    Args:
        date_value: Date string or None

    Returns:
        Date object or None
    """
    if not date_value:
        return None
    try:
        if isinstance(date_value, str):
            return datetime.fromisoformat(date_value).date()
        return date_value
    except (ValueError, AttributeError):
        logger.warning("Failed to parse date: %s", date_value)
        return None


def link_event_to_defendant(event_id: int, defendant_id: int, db: Session) -> bool:
    """Link an event to a defendant.

    Args:
        event_id: ID of the event
        defendant_id: ID of the defendant
        db: Database session

    Returns:
        True if link created, False otherwise
    """
    from app.models.entities import EventDefendant

    # Check for existing link
    existing = (
        db.query(EventDefendant)
        .filter(
            EventDefendant.event_id == event_id,
            EventDefendant.defendant_id == defendant_id,
        )
        .first()
    )
    if existing:
        logger.info("Event-defendant link already exists: event=%d, defendant=%d", event_id, defendant_id)
        return False

    # Create link
    link = EventDefendant(
        event_id=event_id,
        defendant_id=defendant_id,
    )
    db.add(link)
    db.commit()

    logger.info("Linked event %d to defendant %d", event_id, defendant_id)
    return True


def validate_event_data(event_data: Dict) -> Dict[str, list]:
    """Validate event data before ingestion.

    Args:
        event_data: Dictionary containing event data

    Returns:
        Dictionary with validation errors and warnings
    """
    errors = []
    warnings = []

    # Check required fields
    required_fields = ["event_id", "case_id", "court_id", "event_type", "title", "summary"]
    for field in required_fields:
        if field not in event_data or not event_data[field]:
            errors.append(f"Missing required field: {field}")

    # Validate field types
    if "event_type" in event_data and len(event_data["event_type"]) > 80:
        errors.append("event_type exceeds maximum length of 80 characters")

    if "title" in event_data and len(event_data["title"]) > 500:
        errors.append("title exceeds maximum length of 500 characters")

    # Validate dates
    for date_field in ["decision_date", "posted_date"]:
        if date_field in event_data and event_data[date_field]:
            parsed = _parse_date(event_data[date_field])
            if not parsed:
                errors.append(f"Invalid date format for {date_field}")

    # Warnings
    if "decision_result" not in event_data:
        warnings.append("decision_result not provided")

    if "verified_flag" not in event_data:
        warnings.append("verified_flag not provided, defaulting to False")

    return {"errors": errors, "warnings": warnings}
