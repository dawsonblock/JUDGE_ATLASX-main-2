"""Test legal-specific contradiction rules.

Tests for legal-specific contradiction detection including:
- case_status_conflict
- sentence_conflict
- appeal_outcome_conflict
- statute_version_conflict
- court_level_conflict
- judge_assignment_conflict
- identity_conflict
"""

import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy.orm import Session

from app.models.entities import MemoryClaim, CanonicalEntity, SourceSnapshot, LegalSource
from app.memory.contradiction_engine import detect_contradictions


@pytest.fixture
def test_entity(db_session: Session):
    """Create a test canonical entity."""
    entity = CanonicalEntity(
        entity_type="person",
        canonical_name="Test Person",
        normalized_name="test_person",
    )
    db_session.add(entity)
    db_session.commit()
    db_session.refresh(entity)
    return entity


@pytest.fixture
def test_source(db_session: Session):
    """Create a test legal source."""
    source = LegalSource(
        source_key="test_source",
        source_type="official_court",
        lifecycle_state="enabled_runnable",
        is_active=True,
    )
    db_session.add(source)
    db_session.commit()
    db_session.refresh(source)
    return source


@pytest.fixture
def test_snapshot(db_session: Session, test_source: LegalSource):
    """Create a test source snapshot."""
    snapshot = SourceSnapshot(
        source_id=test_source.id,
        source_key="test_source",
        content_hash="abc123",
        fetched_at=datetime.now(timezone.utc),
        parser_version="1.0",
    )
    db_session.add(snapshot)
    db_session.commit()
    db_session.refresh(snapshot)
    return snapshot


def test_case_status_conflict_detection(
    db_session: Session,
    test_entity: CanonicalEntity,
    test_snapshot: SourceSnapshot,
):
    """Test detection of case status contradictions."""
    # Create claim with case_status = convicted
    claim1 = MemoryClaim(
        entity_id=test_entity.id,
        predicate="case_status",
        normalized_value="convicted",
        object_value_type="string",
        claim_type="attribute",
        status="active",
        is_active=True,
        confidence=0.95,
        source_snapshot_id=test_snapshot.id,
        observed_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    db_session.add(claim1)

    # Create claim with case_status = acquitted (contradiction)
    claim2 = MemoryClaim(
        entity_id=test_entity.id,
        predicate="case_status",
        normalized_value="acquitted",
        object_value_type="string",
        claim_type="attribute",
        status="active",
        is_active=True,
        confidence=0.95,
        source_snapshot_id=test_snapshot.id,
        observed_at=datetime.now(timezone.utc) - timedelta(days=3),
    )
    db_session.add(claim2)
    db_session.commit()

    # Detect contradictions
    contradictions = detect_contradictions([claim1, claim2], db_session, persist=False)

    # Should detect case status contradiction
    assert len(contradictions) > 0
    case_status_conflicts = [c for c in contradictions if "case_status" in str(c.get("type", ""))]
    assert len(case_status_conflicts) > 0


def test_sentence_conflict_detection(
    db_session: Session,
    test_entity: CanonicalEntity,
    test_snapshot: SourceSnapshot,
):
    """Test detection of sentence contradictions."""
    # Create claim with sentence = 5 years
    claim1 = MemoryClaim(
        entity_id=test_entity.id,
        predicate="sentence",
        normalized_value="5 years",
        object_value_type="string",
        claim_type="attribute",
        status="active",
        is_active=True,
        confidence=0.95,
        source_snapshot_id=test_snapshot.id,
        observed_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    db_session.add(claim1)

    # Create claim with sentence = 10 years (contradiction)
    claim2 = MemoryClaim(
        entity_id=test_entity.id,
        predicate="sentence",
        normalized_value="10 years",
        object_value_type="string",
        claim_type="attribute",
        status="active",
        is_active=True,
        confidence=0.95,
        source_snapshot_id=test_snapshot.id,
        observed_at=datetime.now(timezone.utc) - timedelta(days=3),
    )
    db_session.add(claim2)
    db_session.commit()

    # Detect contradictions
    contradictions = detect_contradictions([claim1, claim2], db_session, persist=False)

    # Should detect sentence contradiction
    assert len(contradictions) > 0
    sentence_conflicts = [c for c in contradictions if "sentence" in str(c.get("type", ""))]
    assert len(sentence_conflicts) > 0


def test_appeal_outcome_conflict_detection(
    db_session: Session,
    test_entity: CanonicalEntity,
    test_snapshot: SourceSnapshot,
):
    """Test detection of appeal outcome contradictions."""
    # Create claim with appeal_outcome = affirmed
    claim1 = MemoryClaim(
        entity_id=test_entity.id,
        predicate="appeal_outcome",
        normalized_value="affirmed",
        object_value_type="string",
        claim_type="attribute",
        status="active",
        is_active=True,
        confidence=0.95,
        source_snapshot_id=test_snapshot.id,
        observed_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    db_session.add(claim1)

    # Create claim with appeal_outcome = reversed (contradiction)
    claim2 = MemoryClaim(
        entity_id=test_entity.id,
        predicate="appeal_outcome",
        normalized_value="reversed",
        object_value_type="string",
        claim_type="attribute",
        status="active",
        is_active=True,
        confidence=0.95,
        source_snapshot_id=test_snapshot.id,
        observed_at=datetime.now(timezone.utc) - timedelta(days=3),
    )
    db_session.add(claim2)
    db_session.commit()

    # Detect contradictions
    contradictions = detect_contradictions([claim1, claim2], db_session, persist=False)

    # Should detect appeal outcome contradiction
    assert len(contradictions) > 0
    appeal_conflicts = [c for c in contradictions if "appeal" in str(c.get("type", ""))]
    assert len(appeal_conflicts) > 0


def test_statute_version_conflict_detection(
    db_session: Session,
    test_entity: CanonicalEntity,
    test_snapshot: SourceSnapshot,
):
    """Test detection of statute version contradictions."""
    # Create claim with statute_section = s.123(1) (old version)
    claim1 = MemoryClaim(
        entity_id=test_entity.id,
        predicate="statute_section",
        normalized_value="s.123(1)",
        object_value_type="string",
        claim_type="attribute",
        status="active",
        is_active=True,
        confidence=0.95,
        source_snapshot_id=test_snapshot.id,
        observed_at=datetime.now(timezone.utc) - timedelta(days=10),
    )
    db_session.add(claim1)

    # Create claim with statute_section = s.123(2) (newer version, supersession)
    claim2 = MemoryClaim(
        entity_id=test_entity.id,
        predicate="statute_section",
        normalized_value="s.123(2)",
        object_value_type="string",
        claim_type="attribute",
        status="active",
        is_active=True,
        confidence=0.95,
        source_snapshot_id=test_snapshot.id,
        observed_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    db_session.add(claim2)
    db_session.commit()

    # Detect contradictions
    contradictions = detect_contradictions([claim1, claim2], db_session, persist=False)

    # Should detect statute version contradiction (supersession)
    assert len(contradictions) > 0
    statute_conflicts = [c for c in contradictions if "statute" in str(c.get("type", ""))]
    assert len(statute_conflicts) > 0


def test_court_level_conflict_detection(
    db_session: Session,
    test_entity: CanonicalEntity,
    test_snapshot: SourceSnapshot,
):
    """Test detection of court level contradictions."""
    # Create claim with court_level = trial_court
    claim1 = MemoryClaim(
        entity_id=test_entity.id,
        predicate="court_level",
        normalized_value="trial_court",
        object_value_type="string",
        claim_type="attribute",
        status="active",
        is_active=True,
        confidence=0.95,
        source_snapshot_id=test_snapshot.id,
        observed_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    db_session.add(claim1)

    # Create claim with court_level = appellate_court (contradiction for same case)
    claim2 = MemoryClaim(
        entity_id=test_entity.id,
        predicate="court_level",
        normalized_value="appellate_court",
        object_value_type="string",
        claim_type="attribute",
        status="active",
        is_active=True,
        confidence=0.95,
        source_snapshot_id=test_snapshot.id,
        observed_at=datetime.now(timezone.utc) - timedelta(days=3),
    )
    db_session.add(claim2)
    db_session.commit()

    # Detect contradictions
    contradictions = detect_contradictions([claim1, claim2], db_session, persist=False)

    # Should detect court level contradiction
    assert len(contradictions) > 0
    court_conflicts = [c for c in contradictions if "court" in str(c.get("type", ""))]
    assert len(court_conflicts) > 0


def test_judge_assignment_conflict_detection(
    db_session: Session,
    test_entity: CanonicalEntity,
    test_snapshot: SourceSnapshot,
):
    """Test detection of judge assignment contradictions."""
    # Create claim with assigned_judge = Judge Smith
    claim1 = MemoryClaim(
        entity_id=test_entity.id,
        predicate="assigned_judge",
        normalized_value="Judge Smith",
        object_value_type="string",
        claim_type="attribute",
        status="active",
        is_active=True,
        confidence=0.95,
        source_snapshot_id=test_snapshot.id,
        observed_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    db_session.add(claim1)

    # Create claim with assigned_judge = Judge Jones (contradiction)
    claim2 = MemoryClaim(
        entity_id=test_entity.id,
        predicate="assigned_judge",
        normalized_value="Judge Jones",
        object_value_type="string",
        claim_type="attribute",
        status="active",
        is_active=True,
        confidence=0.95,
        source_snapshot_id=test_snapshot.id,
        observed_at=datetime.now(timezone.utc) - timedelta(days=3),
    )
    db_session.add(claim2)
    db_session.commit()

    # Detect contradictions
    contradictions = detect_contradictions([claim1, claim2], db_session, persist=False)

    # Should detect judge assignment contradiction
    assert len(contradictions) > 0
    judge_conflicts = [c for c in contradictions if "judge" in str(c.get("type", ""))]
    assert len(judge_conflicts) > 0


def test_identity_conflict_detection(
    db_session: Session,
    test_snapshot: SourceSnapshot,
):
    """Test detection of identity contradictions (same person, different names)."""
    # Create entity 1
    entity1 = CanonicalEntity(
        entity_type="person",
        canonical_name="John Smith",
        normalized_name="john_smith",
    )
    db_session.add(entity1)
    db_session.flush()

    # Create entity 2
    entity2 = CanonicalEntity(
        entity_type="person",
        canonical_name="Johnathan Smith",
        normalized_name="johnathan_smith",
    )
    db_session.add(entity2)
    db_session.flush()

    # Create claim linking entity1 to entity2 as same person
    claim1 = MemoryClaim(
        entity_id=entity1.id,
        predicate="same_as",
        normalized_value=str(entity2.id),
        object_value_type="entity_id",
        claim_type="identity",
        status="active",
        is_active=True,
        confidence=0.95,
        source_snapshot_id=test_snapshot.id,
        observed_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    db_session.add(claim1)

    # Create claim linking entity1 to entity3 (different person) as same person
    entity3 = CanonicalEntity(
        entity_type="person",
        canonical_name="Jane Doe",
        normalized_name="jane_doe",
    )
    db_session.add(entity3)
    db_session.flush()

    claim2 = MemoryClaim(
        entity_id=entity1.id,
        predicate="same_as",
        normalized_value=str(entity3.id),
        object_value_type="entity_id",
        claim_type="identity",
        status="active",
        is_active=True,
        confidence=0.95,
        source_snapshot_id=test_snapshot.id,
        observed_at=datetime.now(timezone.utc) - timedelta(days=3),
    )
    db_session.add(claim2)
    db_session.commit()

    # Detect contradictions
    contradictions = detect_contradictions([claim1, claim2], db_session, persist=False)

    # Should detect identity contradiction
    assert len(contradictions) > 0
    identity_conflicts = [c for c in contradictions if "identity" in str(c.get("type", ""))]
    assert len(identity_conflicts) > 0


def test_severity_calculation_for_conflicts(
    db_session: Session,
    test_entity: CanonicalEntity,
    test_snapshot: SourceSnapshot,
):
    """Test that legal contradictions have appropriate severity levels."""
    # Create conflicting case status claims
    claim1 = MemoryClaim(
        entity_id=test_entity.id,
        predicate="case_status",
        normalized_value="convicted",
        object_value_type="string",
        claim_type="attribute",
        status="active",
        is_active=True,
        confidence=0.95,
        source_snapshot_id=test_snapshot.id,
        observed_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    db_session.add(claim1)

    claim2 = MemoryClaim(
        entity_id=test_entity.id,
        predicate="case_status",
        normalized_value="acquitted",
        object_value_type="string",
        claim_type="attribute",
        status="active",
        is_active=True,
        confidence=0.95,
        source_snapshot_id=test_snapshot.id,
        observed_at=datetime.now(timezone.utc) - timedelta(days=3),
    )
    db_session.add(claim2)
    db_session.commit()

    # Detect contradictions
    contradictions = detect_contradictions([claim1, claim2], db_session, persist=False)

    # Should have severity information
    assert len(contradictions) > 0
    for contradiction in contradictions:
        assert "severity" in contradiction
        assert contradiction["severity"] in ["low", "medium", "high", "critical"]
