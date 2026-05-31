"""Tests for deterministic claim extraction in extract_claims.py.

Covers all eight claim types:
  entity_type, name_mention, role, bail_decision, sentence_length,
  court_appearance, charge_type, disposition.
"""

from __future__ import annotations

import datetime

import pytest

from app.db.session import SessionLocal
from app.memory.extract_claims import extract_claims
from app.models.entities import (
    CanonicalEntity,
    SourceRegistry,
    SourceSnapshot,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_source(db, key: str) -> SourceRegistry:
    reg = db.query(SourceRegistry).filter_by(source_key=key).first()
    if reg:
        return reg
    reg = SourceRegistry(
        source_key=key,
        source_name=key,
        source_tier="court_direct",
        is_active=True,
        requires_manual_review=False,
        auto_publish_enabled=False,
    )
    db.add(reg)
    db.flush()
    return reg


def _make_entity(db, name: str, etype: str = "judge") -> CanonicalEntity:
    e = CanonicalEntity(
        entity_type=etype,
        canonical_name=name,
        confidence_score=0.9,
    )
    db.add(e)
    db.flush()
    return e


def _make_snapshot(db, source_key: str, text: str) -> SourceSnapshot:
    snap = SourceSnapshot(
        source_key=source_key,
        source_url=f"https://example.com/{source_key}",
        fetched_at=datetime.datetime.utcnow(),
        content_hash="ec1234ab",
        http_status=200,
        is_truncated=False,
        storage_backend="memory",
        original_content_hash="ec1234ab",
        extracted_text=text,
    )
    db.add(snap)
    db.flush()
    return snap


# ---------------------------------------------------------------------------
# entity_type claim
# ---------------------------------------------------------------------------


def test_entity_type_claim_emitted_when_text_present(db_session):
    _make_source(db_session, "ec_src")
    entity = _make_entity(db_session, "Emilia Crane", etype="judge")
    snap = _make_snapshot(db_session, "ec_src", "Emilia Crane presided over the trial.")
    claims = extract_claims(snap, entity, db_session)
    types = [c["claim_type"] for c in claims]
    assert "entity_type" in types
    et_claim = next(c for c in claims if c["claim_type"] == "entity_type")
    assert et_claim["claim_value"] == "judge"
    assert et_claim["confidence"] == 1.0


def test_entity_type_claim_not_emitted_for_empty_text(db_session):
    _make_source(db_session, "ec_empty_src")
    entity = _make_entity(db_session, "Empty Judge")
    snap = _make_snapshot(db_session, "ec_empty_src", "")
    claims = extract_claims(snap, entity, db_session)
    assert claims == []


# ---------------------------------------------------------------------------
# name_mention claim
# ---------------------------------------------------------------------------


def test_name_mention_emitted_when_name_in_text(db_session):
    _make_source(db_session, "nm_src")
    entity = _make_entity(db_session, "Harold Finch")
    snap = _make_snapshot(
        db_session, "nm_src", "The honourable Harold Finch ruled today."
    )
    claims = extract_claims(snap, entity, db_session)
    types = [c["claim_type"] for c in claims]
    assert "name_mention" in types
    nm = next(c for c in claims if c["claim_type"] == "name_mention")
    assert nm["span_start"] is not None
    assert nm["span_end"] > nm["span_start"]
    assert nm["claim_value"] == "harold finch"


def test_name_mention_not_emitted_when_name_absent(db_session):
    _make_source(db_session, "nm_absent_src")
    entity = _make_entity(db_session, "Absent Judge")
    snap = _make_snapshot(
        db_session, "nm_absent_src", "Some text about another person entirely."
    )
    claims = extract_claims(snap, entity, db_session)
    types = [c["claim_type"] for c in claims]
    assert "name_mention" not in types


# ---------------------------------------------------------------------------
# role claim
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "role_text,expected_role",
    [
        ("district judge presided", "district judge"),
        ("circuit judge wrote the opinion", "circuit judge"),
        ("magistrate judge signed the warrant", "magistrate judge"),
        ("chief judge of the court", "chief judge"),
        ("senior judge Patricia Lane", "senior judge"),
    ],
)
def test_role_claim_extracted(db_session, role_text, expected_role):
    src_key = f"role_src_{expected_role.replace(' ', '_')}"
    _make_source(db_session, src_key)
    entity = _make_entity(db_session, "Patricia Lane")
    text = f"Patricia Lane serves as {role_text}."
    snap = _make_snapshot(db_session, src_key, text)
    claims = extract_claims(snap, entity, db_session)
    role_claims = [c for c in claims if c["claim_type"] == "role"]
    roles_found = [c["claim_value"] for c in role_claims]
    assert expected_role in roles_found


# ---------------------------------------------------------------------------
# bail_decision claim
# ---------------------------------------------------------------------------


def test_bail_granted(db_session):
    _make_source(db_session, "bail_granted_src")
    entity = _make_entity(db_session, "Marcus Webb", etype="defendant")
    snap = _make_snapshot(
        db_session,
        "bail_granted_src",
        "Marcus Webb appeared in court. Bail was granted.",
    )
    claims = extract_claims(snap, entity, db_session)
    bail = next((c for c in claims if c["claim_type"] == "bail_decision"), None)
    assert bail is not None
    assert bail["claim_value"] == "granted"
    assert bail["confidence"] == pytest.approx(0.85)


def test_bail_denied(db_session):
    _make_source(db_session, "bail_denied_src")
    entity = _make_entity(db_session, "Sandra Vance", etype="defendant")
    snap = _make_snapshot(
        db_session,
        "bail_denied_src",
        "Sandra Vance was ordered detained pending trial.",
    )
    claims = extract_claims(snap, entity, db_session)
    bail = next((c for c in claims if c["claim_type"] == "bail_decision"), None)
    assert bail is not None
    assert bail["claim_value"] == "denied"


def test_bail_not_emitted_when_no_bail_text(db_session):
    _make_source(db_session, "bail_absent_src")
    entity = _make_entity(db_session, "Quiet Defendant", etype="defendant")
    snap = _make_snapshot(
        db_session,
        "bail_absent_src",
        "Quiet Defendant scheduled for hearing on Monday.",
    )
    claims = extract_claims(snap, entity, db_session)
    types = [c["claim_type"] for c in claims]
    assert "bail_decision" not in types


# ---------------------------------------------------------------------------
# sentence_length claim
# ---------------------------------------------------------------------------


def test_sentence_years(db_session):
    _make_source(db_session, "sent_years_src")
    entity = _make_entity(db_session, "Owen Dale", etype="defendant")
    snap = _make_snapshot(
        db_session, "sent_years_src", "Owen Dale was sentenced to 5 years in prison."
    )
    claims = extract_claims(snap, entity, db_session)
    sent = next((c for c in claims if c["claim_type"] == "sentence_length"), None)
    assert sent is not None
    assert "5 year" in sent["claim_value"]
    assert sent["confidence"] == pytest.approx(0.88)


def test_sentence_life(db_session):
    _make_source(db_session, "sent_life_src")
    entity = _make_entity(db_session, "Leo Marsh", etype="defendant")
    snap = _make_snapshot(
        db_session,
        "sent_life_src",
        "Leo Marsh received life in prison for the offence.",
    )
    claims = extract_claims(snap, entity, db_session)
    sent = next((c for c in claims if c["claim_type"] == "sentence_length"), None)
    assert sent is not None
    assert "life" in sent["claim_value"]


def test_sentence_probation(db_session):
    _make_source(db_session, "sent_prob_src")
    entity = _make_entity(db_session, "Nina Cross", etype="defendant")
    snap = _make_snapshot(
        db_session, "sent_prob_src", "Nina Cross was given 3 years of probation."
    )
    claims = extract_claims(snap, entity, db_session)
    sent = next((c for c in claims if c["claim_type"] == "sentence_length"), None)
    assert sent is not None
    assert "probation" in sent["claim_value"]


# ---------------------------------------------------------------------------
# court_appearance claim
# ---------------------------------------------------------------------------


def test_court_appearance_arraigned(db_session):
    _make_source(db_session, "appear_arraigned_src")
    entity = _make_entity(db_session, "Terry Bloom", etype="defendant")
    snap = _make_snapshot(
        db_session,
        "appear_arraigned_src",
        "Terry Bloom was arraigned in federal court.",
    )
    claims = extract_claims(snap, entity, db_session)
    appear = next((c for c in claims if c["claim_type"] == "court_appearance"), None)
    assert appear is not None
    assert appear["confidence"] == pytest.approx(0.75)


def test_court_appearance_hearing(db_session):
    _make_source(db_session, "appear_hearing_src")
    entity = _make_entity(db_session, "Grace Simmons")
    snap = _make_snapshot(
        db_session,
        "appear_hearing_src",
        "Grace Simmons appeared for a preliminary hearing.",
    )
    claims = extract_claims(snap, entity, db_session)
    types = [c["claim_type"] for c in claims]
    assert "court_appearance" in types


# ---------------------------------------------------------------------------
# charge_type claim
# ---------------------------------------------------------------------------


def test_charge_type_charged_with(db_session):
    _make_source(db_session, "charge_cw_src")
    entity = _make_entity(db_session, "Philip Burns", etype="defendant")
    snap = _make_snapshot(
        db_session,
        "charge_cw_src",
        "Philip Burns was charged with wire fraud in the indictment.",
    )
    claims = extract_claims(snap, entity, db_session)
    charge = next((c for c in claims if c["claim_type"] == "charge_type"), None)
    assert charge is not None
    assert "wire fraud" in charge["claim_value"]
    assert charge["confidence"] == pytest.approx(0.82)


def test_charge_type_counts_of(db_session):
    _make_source(db_session, "charge_counts_src")
    entity = _make_entity(db_session, "Ava Stone", etype="defendant")
    snap = _make_snapshot(
        db_session,
        "charge_counts_src",
        "Ava Stone faced three counts of money laundering.",
    )
    claims = extract_claims(snap, entity, db_session)
    charge = next((c for c in claims if c["claim_type"] == "charge_type"), None)
    assert charge is not None
    assert "money laundering" in charge["claim_value"]


# ---------------------------------------------------------------------------
# disposition claim
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Dale Pryor was convicted of the charges.", "convicted"),
        ("Dale Pryor was found guilty on all counts.", "convicted"),
        ("Dale Pryor was acquitted by the jury.", "acquitted"),
        ("The case was dismissed at the request of the prosecutor.", "dismissed"),
        ("Dale Pryor pled guilty to one count.", "convicted"),
    ],
)
def test_disposition_outcomes(db_session, text, expected):
    src_key = f"disp_src_{expected}_{hash(text) & 0xFFFF:04x}"
    _make_source(db_session, src_key)
    entity = _make_entity(db_session, "Dale Pryor", etype="defendant")
    snap = _make_snapshot(db_session, src_key, text)
    claims = extract_claims(snap, entity, db_session)
    disp = next((c for c in claims if c["claim_type"] == "disposition"), None)
    assert disp is not None
    assert disp["claim_value"] == expected
    assert disp["confidence"] == pytest.approx(0.87)


# ---------------------------------------------------------------------------
# Full-text fallback when entity name is not in text
# ---------------------------------------------------------------------------


def test_full_text_fallback_extracts_bail_when_no_name_match(db_session):
    """When entity name is absent, claims should still be extracted from full text."""
    _make_source(db_session, "fallback_src")
    entity = _make_entity(db_session, "Unknown Person", etype="defendant")
    snap = _make_snapshot(
        db_session, "fallback_src", "The defendant's bail was denied by the court."
    )
    claims = extract_claims(snap, entity, db_session)
    bail = next((c for c in claims if c["claim_type"] == "bail_decision"), None)
    assert bail is not None


# ---------------------------------------------------------------------------
# claim_value_json extra field
# ---------------------------------------------------------------------------


def test_bail_claim_has_outcome_in_extra(db_session):
    _make_source(db_session, "bail_extra_src")
    entity = _make_entity(db_session, "Ernest Fox", etype="defendant")
    snap = _make_snapshot(
        db_session, "bail_extra_src", "Ernest Fox's bail was granted by the court."
    )
    claims = extract_claims(snap, entity, db_session)
    bail = next((c for c in claims if c["claim_type"] == "bail_decision"), None)
    assert bail is not None
    assert isinstance(bail["claim_value_json"], dict)
    assert "outcome" in bail["claim_value_json"]
