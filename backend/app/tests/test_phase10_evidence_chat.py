"""Phase 10: AI evidence chat service tests.

Tests cover:
- Service layer (evidence_chat.py): question sanitization, entity gating,
  evidence ranking, citation assembly, disclaimer presence.
- API route (POST /api/chat/evidence): request validation, DB-backed responses,
  public-only evidence guard.
"""

from __future__ import annotations

import itertools
import hashlib
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from app.models.entities import (
    CrimeIncident,
    CrimeIncidentEventLink,
    Event,
    RelationshipEvidence,
    SourceSnapshot,
)
from app.policies.publication_policy import CORRECTED
from app.services.evidence_chat import (
    _MAX_CITATIONS,
    _MAX_QUESTION_LEN,
    _sanitize_question,
    _score_evidence,
    chat_about_evidence,
)

_id_counter = itertools.count(1)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_incident(db, *, is_public: bool = True) -> CrimeIncident:
    uid = next(_id_counter)
    
    # Create a source snapshot if incident is public (required for evidence_anchor_status)
    source_snapshot_id = None
    if is_public:
        content = f"test snapshot {uid}".encode("utf-8")
        snapshot = SourceSnapshot(
            source_key="test_source",
            source_url="https://example.test",
            fetched_at=datetime.now(timezone.utc),
            content_hash=hashlib.sha256(content).hexdigest(),
            raw_content=content.decode("utf-8"),
            storage_backend="db",
        )
        db.add(snapshot)
        db.flush()
        source_snapshot_id = snapshot.id
    
    inc = CrimeIncident(
        source_id=None,
        external_id=f"CHAT-TEST-{uid}",
        incident_type="assault",
        incident_category="violent",
        city="TestCity",
        country="CA",
        source_name="test_source",
        is_public=is_public,
        verification_status="unverified",
        review_status=CORRECTED if is_public else "pending_review",
        source_snapshot_id=source_snapshot_id,
        latitude_public=51.5 if is_public else None,  # London, UK
        longitude_public=-0.1 if is_public else None,
        precision_level="city_centroid",
    )
    db.add(inc)
    db.flush()
    return inc


def _make_evidence(
    db,
    *,
    entity_type: str = "crime_incident",
    entity_id: int,
    relationship_type: str = "suspect",
    evidence_type: str = "source_record",
    evidence_source: str = "mock_source",
    excerpt: str | None = None,
    confidence: float = 0.8,
    relationship_status: str | None = "approved",
) -> RelationshipEvidence:
    # Create a source snapshot for the evidence
    content = f"evidence snapshot {next(_id_counter)}".encode("utf-8")
    snapshot = SourceSnapshot(
        source_key=evidence_source,
        source_url="https://example.test/evidence",
        fetched_at=datetime.now(timezone.utc),
        content_hash=hashlib.sha256(content).hexdigest(),
        raw_content=content.decode("utf-8"),
        storage_backend="db",
    )
    db.add(snapshot)
    db.flush()
    
    ev = RelationshipEvidence(
        from_entity_type=entity_type,
        from_entity_id=entity_id,
        to_entity_type="person",
        to_entity_id=next(_id_counter),
        relationship_type=relationship_type,
        evidence_type=evidence_type,
        evidence_source=evidence_source,
        evidence_excerpt=excerpt,
        extracted_by="test_runner",
        confidence=confidence,
        public_visibility=True,
        relationship_status=relationship_status,
        verification_status="verified",
        review_status="verified_court_record",
        evidence_snapshot_id=snapshot.id,
    )
    db.add(ev)
    db.flush()
    return ev


# ---------------------------------------------------------------------------
# _sanitize_question
# ---------------------------------------------------------------------------


def test_sanitize_strips_control_chars():
    assert "\x00" not in _sanitize_question("hello\x00world")


def test_sanitize_enforces_length():
    long_q = "a" * (_MAX_QUESTION_LEN + 100)
    assert len(_sanitize_question(long_q)) == _MAX_QUESTION_LEN


def test_sanitize_preserves_normal_text():
    q = "What happened on March 5?"
    assert _sanitize_question(q) == q


# ---------------------------------------------------------------------------
# chat_about_evidence – service layer
# ---------------------------------------------------------------------------


def test_no_entity_returns_no_evidence(db_session):
    result = chat_about_evidence(db_session, "what happened?")
    assert "no public evidence" in result.answer.lower()
    assert result.citations == []
    assert result.unsupported_claims
    assert result.safety_notes


def test_nonpublic_incident_returns_no_evidence(db_session):
    inc = _make_incident(db_session, is_public=False)
    _make_evidence(db_session, entity_id=inc.id)
    result = chat_about_evidence(db_session, "tell me more", incident_id=inc.id)
    assert result.citations == []
    assert not result.incident_found


def test_public_incident_no_evidence_rows(db_session):
    inc = _make_incident(db_session, is_public=True)
    result = chat_about_evidence(db_session, "any evidence?", incident_id=inc.id)
    assert result.incident_found is True
    assert result.citations == []
    assert "no relationship evidence" in result.answer.lower()


def test_public_incident_returns_citations(db_session):
    inc = _make_incident(db_session, is_public=True)
    _make_evidence(db_session, entity_id=inc.id, excerpt="arrest at scene")
    result = chat_about_evidence(db_session, "any evidence?", incident_id=inc.id)
    assert result.incident_found is True
    assert len(result.citations) == 1
    assert result.citations[0].evidence_id is not None
    assert result.unsupported_claims == []
    assert result.safety_notes


def test_answer_contains_count(db_session):
    inc = _make_incident(db_session, is_public=True)
    for i in range(3):
        _make_evidence(db_session, entity_id=inc.id, excerpt=f"evidence {i}")
    result = chat_about_evidence(
        db_session, "what evidence exists?", incident_id=inc.id
    )
    assert "3" in result.answer


def test_citations_capped_at_max(db_session):
    inc = _make_incident(db_session, is_public=True)
    for i in range(_MAX_CITATIONS + 4):
        _make_evidence(db_session, entity_id=inc.id, excerpt=f"row {i}")
    result = chat_about_evidence(db_session, "summarise all", incident_id=inc.id)
    assert len(result.citations) <= _MAX_CITATIONS


def test_disclaimer_always_present(db_session):
    inc = _make_incident(db_session, is_public=True)
    _make_evidence(db_session, entity_id=inc.id)
    result = chat_about_evidence(db_session, "what happened?", incident_id=inc.id)
    assert "innocent" in result.disclaimer.lower()


def test_question_sanitized_before_use(db_session):
    inc = _make_incident(db_session, is_public=True)
    _make_evidence(db_session, entity_id=inc.id, excerpt="assault suspect")
    result = chat_about_evidence(db_session, "assault\x00query", incident_id=inc.id)
    assert "\x00" not in result.question


def test_case_id_evidence_returned(db_session):
    """Evidence linked to a court_case entity is returned when case_id supplied."""
    # Use a seeded event (already linked to a seeded case) to satisfy the guard.
    existing_event = db_session.scalar(select(Event).limit(1))
    assert existing_event is not None, "seed_sample_data must populate events"
    case_id = existing_event.case_id

    # Create a public incident and link it to the seeded event (satisfies the guard).
    inc = _make_incident(db_session, is_public=True)
    link = CrimeIncidentEventLink(
        crime_incident_id=inc.id,
        event_id=existing_event.id,
    )
    db_session.add(link)
    db_session.flush()

    # Create a source snapshot for the evidence
    content = b"court case evidence snapshot"
    snapshot = SourceSnapshot(
        source_key="pacer",
        source_url="https://example.test/pacer",
        fetched_at=datetime.now(timezone.utc),
        content_hash=hashlib.sha256(content).hexdigest(),
        raw_content=content.decode("utf-8"),
        storage_backend="db",
    )
    db_session.add(snapshot)
    db_session.flush()

    ev = RelationshipEvidence(
        from_entity_type="court_case",
        from_entity_id=case_id,
        to_entity_type="person",
        to_entity_id=next(_id_counter),
        relationship_type="defendant",
        evidence_type="court_doc",
        evidence_source="pacer",
        evidence_excerpt="charged with assault",
        extracted_by="test_runner",
        confidence=0.9,
        public_visibility=True,
        relationship_status="approved",
        verification_status="verified",
        review_status="verified_court_record",
        evidence_snapshot_id=snapshot.id,
    )
    db_session.add(ev)
    db_session.flush()
    result = chat_about_evidence(db_session, "who is the defendant?", case_id=case_id)
    assert len(result.citations) == 1
    assert result.citations[0].relationship_type == "defendant"


def test_high_keyword_overlap_ranked_first(db_session):
    inc = _make_incident(db_session, is_public=True)
    # Low-relevance evidence
    _make_evidence(
        db_session, entity_id=inc.id, excerpt="unrelated fiscal report", confidence=0.5
    )
    # High-relevance evidence matching the question
    _make_evidence(
        db_session,
        entity_id=inc.id,
        excerpt="assault weapon discovered at scene",
        confidence=0.5,
    )
    result = chat_about_evidence(db_session, "assault weapon scene", incident_id=inc.id)
    assert "assault" in (result.citations[0].excerpt or "").lower()


# ---------------------------------------------------------------------------
# API route
# ---------------------------------------------------------------------------


def test_post_evidence_chat_allows_legal_context_without_entity(client):
    resp = client.post("/api/chat/evidence", json={"question": "what happened?"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["citations"] == []
    assert "legal_context_citations" in body


def test_post_evidence_chat_question_too_short(client):
    resp = client.post("/api/chat/evidence", json={"question": "hi", "incident_id": 1})
    assert resp.status_code == 422


def test_post_evidence_chat_question_too_long(client):
    resp = client.post(
        "/api/chat/evidence",
        json={"question": "a" * (_MAX_QUESTION_LEN + 1), "incident_id": 1},
    )
    assert resp.status_code == 422


def test_post_evidence_chat_nonexistent_incident_returns_200(client):
    """Non-existent (or private) incident_id → 200 with empty citations."""
    resp = client.post(
        "/api/chat/evidence",
        json={"question": "any evidence?", "incident_id": 99999},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "citations" in body
    assert body["citations"] == []
    assert "disclaimer" in body


def test_post_evidence_chat_valid_returns_structure(client, db_session):
    inc = _make_incident(db_session, is_public=True)
    _make_evidence(
        db_session, entity_id=inc.id, excerpt="police report confirms assault"
    )
    db_session.commit()

    resp = client.post(
        "/api/chat/evidence",
        json={"question": "what evidence exists?", "incident_id": inc.id},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["incident_found"] is True
    assert len(body["citations"]) == 1
    assert body["citations"][0]["evidence_type"] == "source_record"
    assert "innocent" in body["disclaimer"].lower()
    assert body["unsupported_claims"] == []
    assert body["safety_notes"]
