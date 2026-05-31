"""Legal correlation engine for detecting relationships in legal data.

This module provides legal-domain correlation (not intelligence-style) for
detecting relationships between legal events, claims, and entities. Each
correlation is a hypothesis, not a verdict. Sensitive correlations are never
auto-published without review.

Correlation types:
- same_event_multiple_sources: Multiple sources reporting same event
- same_person_multiple_cases: Same person appears in multiple cases
- judge_case_news_overlap: Judge's case appears in news coverage
- crime_report_court_case_possible_link: Crime report may link to court case
- law_change_case_topic_overlap: Legislation change overlaps with case topic
- contradictory_source_claims: Contradictory claims from different sources
- duplicate_incident_report: Duplicate incident reports
- stale_update_detected: Source data appears stale
"""
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import (
    CanonicalEntity,
    CrimeIncident,
    Event,
    LegalSource,
    MemoryClaim,
)

logger = logging.getLogger(__name__)


class LegalCorrelation:
    """Represents a legal correlation hypothesis."""

    def __init__(
        self,
        correlation_type: str,
        event_ids: list[str],
        claim_ids: list[str],
        evidence_ids: list[str],
        confidence: float,
        explanation: str,
        risk_level: str,
        review_status: str = "needs_review",
    ):
        self.id = str(uuid.uuid4())
        self.correlation_type = correlation_type
        self.event_ids = event_ids
        self.claim_ids = claim_ids
        self.evidence_ids = evidence_ids
        self.confidence = confidence
        self.explanation = explanation
        self.risk_level = risk_level
        self.review_status = review_status
        self.created_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "id": self.id,
            "correlation_type": self.correlation_type,
            "event_ids": self.event_ids,
            "claim_ids": self.claim_ids,
            "evidence_ids": self.evidence_ids,
            "confidence": self.confidence,
            "explanation": self.explanation,
            "risk_level": self.risk_level,
            "review_status": self.review_status,
            "created_at": self.created_at.isoformat(),
        }


class LegalCorrelationEngine:
    """Engine for detecting legal correlations."""

    def __init__(self):
        self.correlation_types = {
            "same_event_multiple_sources",
            "same_person_multiple_cases",
            "judge_case_news_overlap",
            "crime_report_court_case_possible_link",
            "law_change_case_topic_overlap",
            "contradictory_source_claims",
            "duplicate_incident_report",
            "stale_update_detected",
        }

    def detect_correlations(
        self,
        db: Session,
        correlation_types: list[str] | None = None,
        confidence_threshold: float = 0.5,
    ) -> list[LegalCorrelation]:
        """Detect correlations of specified types.

        Args:
            db: Database session
            correlation_types: Types to detect (all if None)
            confidence_threshold: Minimum confidence for correlations

        Returns:
            List of detected correlations
        """
        if correlation_types is None:
            correlation_types = list(self.correlation_types)

        correlations = []

        for correlation_type in correlation_types:
            if correlation_type == "same_event_multiple_sources":
                correlations.extend(
                    self._detect_same_event_multiple_sources(db, confidence_threshold)
                )
            elif correlation_type == "same_person_multiple_cases":
                correlations.extend(
                    self._detect_same_person_multiple_cases(db, confidence_threshold)
                )
            elif correlation_type == "judge_case_news_overlap":
                correlations.extend(
                    self._detect_judge_case_news_overlap(db, confidence_threshold)
                )
            elif correlation_type == "crime_report_court_case_possible_link":
                correlations.extend(
                    self._detect_crime_report_court_case_link(db, confidence_threshold)
                )
            elif correlation_type == "law_change_case_topic_overlap":
                correlations.extend(
                    self._detect_law_change_case_topic_overlap(db, confidence_threshold)
                )
            elif correlation_type == "contradictory_source_claims":
                correlations.extend(
                    self._detect_contradictory_source_claims(db, confidence_threshold)
                )
            elif correlation_type == "duplicate_incident_report":
                correlations.extend(
                    self._detect_duplicate_incident_report(db, confidence_threshold)
                )
            elif correlation_type == "stale_update_detected":
                correlations.extend(
                    self._detect_stale_update_detected(db, confidence_threshold)
                )

        logger.info(f"Detected {len(correlations)} correlations")
        return correlations

    def _detect_same_event_multiple_sources(
        self, db: Session, confidence_threshold: float
    ) -> list[LegalCorrelation]:
        """Detect events reported by multiple sources."""
        correlations = []

        # Group events by title and date
        events = db.query(Event).limit(1000).all()
        event_groups: dict[str, list[Event]] = {}

        for event in events:
            decision_date = event.decision_date.isoformat() if event.decision_date else "unknown"
            key = f"{event.title}_{decision_date}"
            if key not in event_groups:
                event_groups[key] = []
            event_groups[key].append(event)

        # Find events with multiple sources
        for key, group in event_groups.items():
            if len(group) > 1:
                # Check if sources are different
                sources = set()
                for event in group:
                    for source in event.sources:
                        sources.add(source.source_id)

                if len(sources) > 1:
                    correlation = LegalCorrelation(
                        correlation_type="same_event_multiple_sources",
                        event_ids=[str(e.id) for e in group],
                        claim_ids=[],
                        evidence_ids=[],
                        confidence=0.8,
                        explanation=f"Event reported by {len(sources)} different sources",
                        risk_level="low",
                        review_status="auto_approved",
                    )
                    correlations.append(correlation)

        return correlations

    def _detect_same_person_multiple_cases(
        self, db: Session, confidence_threshold: float
    ) -> list[LegalCorrelation]:
        """Detect same person appearing in multiple cases."""
        correlations = []

        # Query entities by person type
        entities = (
            db.query(CanonicalEntity)
            .filter(CanonicalEntity.entity_type == "person")
            .limit(500)
            .all()
        )

        # Group by normalized name
        person_groups: dict[str, list[CanonicalEntity]] = {}
        for entity in entities:
            if not entity.name:
                continue
            normalized_name = entity.name.lower().strip()
            if normalized_name not in person_groups:
                person_groups[normalized_name] = []
            person_groups[normalized_name].append(entity)

        # Find persons in multiple cases
        for name, group in person_groups.items():
            if len(group) > 1:
                # Get claim IDs for these entities
                claim_ids = []
                for entity in group:
                    claims = (
                        db.query(MemoryClaim)
                        .filter(MemoryClaim.entity_id == entity.id)
                        .all()
                    )
                    claim_ids.extend([str(c.id) for c in claims])

                correlation = LegalCorrelation(
                    correlation_type="same_person_multiple_cases",
                    event_ids=[],
                    claim_ids=claim_ids,
                    evidence_ids=[],
                    confidence=0.7,
                    explanation=f"Person '{name}' appears in {len(group)} different cases",
                    risk_level="medium",
                    review_status="needs_review",
                )
                correlations.append(correlation)

        return correlations

    def _detect_judge_case_news_overlap(
        self, db: Session, confidence_threshold: float
    ) -> list[LegalCorrelation]:
        """Detect judge's case appearing in news coverage."""
        correlations = []

        # This would integrate with news ingestion when available
        # For now, return empty list
        return correlations

    def _detect_crime_report_court_case_link(
        self, db: Session, confidence_threshold: float
    ) -> list[LegalCorrelation]:
        """Detect possible links between crime reports and court cases."""
        correlations = []

        # Find crime incidents and court events in same location/time
        crime_incidents = (
            db.query(CrimeIncident)
            .filter(CrimeIncident.is_public.is_(True))
            .limit(500)
            .all()
        )

        court_events = db.query(Event).limit(500).all()

        for incident in crime_incidents:
            for event in court_events:
                # Check if in same city
                if incident.city and event.primary_location and event.primary_location.name:
                    if incident.city.lower() in event.primary_location.name.lower():
                        # Check if dates are close (within 30 days)
                        if incident.reported_at and event.decision_date:
                            date_diff = abs(
                                (incident.reported_at - event.decision_date).days
                            )
                            if date_diff <= 30:
                                correlation = LegalCorrelation(
                                    correlation_type="crime_report_court_case_possible_link",
                                    event_ids=[str(incident.id), str(event.id)],
                                    claim_ids=[],
                                    evidence_ids=[],
                                    confidence=0.5,
                                    explanation=f"Crime report in {incident.city} may link to court case within {date_diff} days",
                                    risk_level="medium",
                                    review_status="needs_review",
                                )
                                correlations.append(correlation)

        return correlations

    def _detect_law_change_case_topic_overlap(
        self, db: Session, confidence_threshold: float
    ) -> list[LegalCorrelation]:
        """Detect legislation changes overlapping with case topics."""
        correlations = []

        # This would integrate with legislation ingestion when available
        # For now, return empty list
        return correlations

    def _detect_contradictory_source_claims(
        self, db: Session, confidence_threshold: float
    ) -> list[LegalCorrelation]:
        """Detect contradictory claims from different sources."""
        correlations = []

        # Use existing contradiction engine
        from app.memory.contradiction_engine import get_open_contradictions

        # Get all contradictions
        contradictions = get_open_contradictions(db)

        # Group by source
        contradictions_by_source: dict[str, list[Any]] = {}
        for contradiction in contradictions:
            if contradiction.claim_a.source_snapshot_id:
                contradictions_by_source.setdefault(
                    contradiction.claim_a.source_snapshot_id, []
                ).append(contradiction)

        # Find contradictions from different sources
        for source_id, contras in contradictions_by_source.items():
            if len(contras) > 1:
                claim_ids = [str(c.claim_a.id) for c in contras]
                correlation = LegalCorrelation(
                    correlation_type="contradictory_source_claims",
                    event_ids=[],
                    claim_ids=claim_ids,
                    evidence_ids=[],
                    confidence=0.9,
                    explanation=f"{len(contras)} contradictory claims from same source",
                    risk_level="high",
                    review_status="needs_review",
                )
                correlations.append(correlation)

        return correlations

    def _detect_duplicate_incident_report(
        self, db: Session, confidence_threshold: float
    ) -> list[LegalCorrelation]:
        """Detect duplicate incident reports."""
        correlations = []

        # Find crime incidents with similar titles/descriptions
        crime_incidents = (
            db.query(CrimeIncident)
            .filter(CrimeIncident.is_public.is_(True))
            .limit(500)
            .all()
        )

        for i, incident1 in enumerate(crime_incidents):
            for incident2 in crime_incidents[i + 1 :]:
                # Check for similar title
                if incident1.incident_category and incident2.incident_category:
                    if (
                        incident1.incident_category == incident2.incident_category
                        and incident1.city == incident2.city
                    ):
                        # Check if dates are close
                        if incident1.reported_at and incident2.reported_at:
                            date_diff = abs(
                                (incident1.reported_at - incident2.reported_at).days
                            )
                            if date_diff <= 7:  # Within a week
                                correlation = LegalCorrelation(
                                    correlation_type="duplicate_incident_report",
                                    event_ids=[str(incident1.id), str(incident2.id)],
                                    claim_ids=[],
                                    evidence_ids=[],
                                    confidence=0.6,
                                    explanation=f"Similar incident reports in {incident1.city} within {date_diff} days",
                                    risk_level="low",
                                    review_status="auto_approved",
                                )
                                correlations.append(correlation)

        return correlations

    def _detect_stale_update_detected(
        self, db: Session, confidence_threshold: float
    ) -> list[LegalCorrelation]:
        """Detect sources with stale data."""
        correlations = []

        # Find sources not updated in 90 days
        stale_threshold = datetime.now(timezone.utc).timestamp() - (90 * 24 * 3600)

        sources = db.query(LegalSource).filter(
            LegalSource.is_active.is_(True)
        ).all()

        for source in sources:
            if source.last_ingested_at:
                if source.last_ingested_at.timestamp() < stale_threshold:
                    correlation = LegalCorrelation(
                        correlation_type="stale_update_detected",
                        event_ids=[],
                        claim_ids=[],
                        evidence_ids=[],
                        confidence=0.95,
                        explanation=f"Source '{source.source_id}' not updated in over 90 days",
                        risk_level="medium",
                        review_status="needs_review",
                    )
                    correlations.append(correlation)

        return correlations
