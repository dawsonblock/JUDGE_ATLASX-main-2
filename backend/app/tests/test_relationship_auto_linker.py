"""Unit tests for app.services.relationship_auto_linker."""

import uuid
from unittest.mock import MagicMock, patch

import pytest

from app.services.relationship_auto_linker import (
    LinkResult,
    _normalize_docket,
    auto_link_by_courtlistener_id,
    auto_link_by_docket,
    auto_link_by_name_only,
)


# ---------------------------------------------------------------------------
# _normalize_docket helper
# ---------------------------------------------------------------------------


def test_normalize_docket_strips_spaces_and_dashes():
    assert _normalize_docket("2025-CR-001") == "2025CR001"


def test_normalize_docket_uppercases():
    assert _normalize_docket("2025cr001") == "2025CR001"


def test_normalize_docket_handles_inner_spaces():
    assert _normalize_docket("2025 CR 001") == "2025CR001"


def test_normalize_docket_empty_string():
    assert _normalize_docket("") == ""


# ---------------------------------------------------------------------------
# auto_link_by_docket
# ---------------------------------------------------------------------------


def test_docket_empty_returns_skip():
    db = MagicMock()
    result = auto_link_by_docket(db, "crime_incident", 1, "", "test_source")
    assert result.action == "skip"
    assert result.confidence == 0.0
    assert "empty_docket_number" in result.reasons


def test_docket_whitespace_returns_skip():
    db = MagicMock()
    result = auto_link_by_docket(db, "crime_incident", 1, "   ", "test_source")
    assert result.action == "skip"


def _make_court_and_case(db_session, docket, norm_docket, **extra):
    """Create a Court + Case row, returning the Case."""
    from app.models.entities import Case, Court, Location

    uid = uuid.uuid4().hex[:8]
    loc = Location(
        name=f"Test Courthouse {uid}",
        location_type="courthouse",
        city="Toronto",
        state="ON",
        latitude=43.65,
        longitude=-79.38,
    )
    db_session.add(loc)
    db_session.flush()

    court = Court(
        courtlistener_id=f"test-court-{uid}",
        name=f"Test Court {uid}",
        jurisdiction="Federal",
        region="CA-ON",
        location_id=loc.id,
    )
    db_session.add(court)
    db_session.flush()

    case = Case(
        court_id=court.id,
        docket_number=docket,
        normalized_docket_number=norm_docket,
        caption="Test v. Test",
        case_type="criminal",
        **extra,
    )
    db_session.add(case)
    db_session.flush()
    return case


def test_docket_single_match_links(db_session):
    """Integration test: exact docket match against real DB."""
    _make_court_and_case(db_session, "2025-TEST-001", "2025TEST001")

    with patch(
        "app.services.relationship_auto_linker.RelationshipEvidenceService"
    ) as MockSvc:
        mock_ev = MagicMock()
        mock_ev.id = 42
        MockSvc.return_value.create_evidence.return_value = mock_ev

        result = auto_link_by_docket(
            db_session,
            "crime_incident",
            99,
            "2025-TEST-001",
            "test_source",
        )

    assert result.action == "link"
    assert result.confidence == 0.95
    assert result.relationship_type == "linked_via_docket"
    assert result.evidence_id == 42
    assert any("2025TEST001" in r for r in result.reasons)


def test_docket_no_match_quarantines(db_session):
    result = auto_link_by_docket(
        db_session,
        "crime_incident",
        1,
        "NONEXISTENT-9999",
        "test_source",
    )
    assert result.action == "quarantine"
    assert result.confidence == 0.35


def test_docket_ambiguous_match_quarantines(db_session):
    # Two cases with same normalized docket (different docket_number to avoid unique constraint)
    for i in range(2):
        _make_court_and_case(
            db_session, f"AMBI-001-DUP-{i}", "AMBI001DUP"
        )

    result = auto_link_by_docket(
        db_session,
        "crime_incident",
        1,
        "AMBI-001-DUP",
        "test_source",
    )
    assert result.action == "quarantine"
    assert any("ambiguous_docket" in r for r in result.reasons)


# ---------------------------------------------------------------------------
# auto_link_by_courtlistener_id
# ---------------------------------------------------------------------------


def test_cl_id_none_returns_skip():
    db = MagicMock()
    result = auto_link_by_courtlistener_id(db, "crime_incident", 1, None, "test_source")
    assert result.action == "skip"
    assert result.confidence == 0.0


def test_cl_id_empty_string_returns_skip():
    db = MagicMock()
    result = auto_link_by_courtlistener_id(db, "crime_incident", 1, "", "test_source")
    assert result.action == "skip"


def test_cl_id_single_match_links(db_session):
    _make_court_and_case(
        db_session, "CL-2025-001", "CL2025001", courtlistener_docket_id="99999"
    )

    with patch(
        "app.services.relationship_auto_linker.RelationshipEvidenceService"
    ) as MockSvc:
        mock_ev = MagicMock()
        mock_ev.id = 77
        MockSvc.return_value.create_evidence.return_value = mock_ev

        result = auto_link_by_courtlistener_id(
            db_session, "crime_incident", 99, "99999", "test_source"
        )

    assert result.action == "link"
    assert result.confidence == 0.90
    assert result.evidence_id == 77


def test_cl_id_no_match_quarantines(db_session):
    result = auto_link_by_courtlistener_id(
        db_session, "crime_incident", 1, "00000000", "test_source"
    )
    assert result.action == "quarantine"
    assert result.confidence == 0.35


# ---------------------------------------------------------------------------
# auto_link_by_name_only — always quarantine
# ---------------------------------------------------------------------------


def test_name_only_always_quarantines():
    db = MagicMock()
    result = auto_link_by_name_only(db, "crime_incident", 1, "John Doe", "test_source")
    assert result.action == "quarantine"
    assert result.confidence == 0.35
    assert result.relationship_type == "same_incident"
    assert result.evidence_id is None


def test_name_only_truncates_long_names():
    db = MagicMock()
    long_name = "A" * 200
    result = auto_link_by_name_only(db, "crime_incident", 1, long_name, "test_source")
    assert result.action == "quarantine"
    assert any(len(r) < 200 for r in result.reasons)


def test_name_only_empty_name():
    db = MagicMock()
    result = auto_link_by_name_only(db, "crime_incident", 1, "", "test_source")
    assert result.action == "quarantine"


# ---------------------------------------------------------------------------
# LinkResult confidence threshold
# ---------------------------------------------------------------------------


def test_auto_link_threshold_respected():
    """link results must be at or above the published threshold."""
    from app.services.relationship_auto_linker import _AUTO_LINK_THRESHOLD

    # Docket match confidence
    assert 0.95 >= _AUTO_LINK_THRESHOLD
    # CL-ID match confidence
    assert 0.90 >= _AUTO_LINK_THRESHOLD
    # Name-only must be below threshold
    assert 0.35 < _AUTO_LINK_THRESHOLD
