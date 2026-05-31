"""Regression tests for public visibility gates.

Proves that:
1.  GET /api/defendants/{id} returns 404 for a non-existent defendant.
2.  GET /api/defendants/{id} returns 404 for a defendant with NO public event.
3.  GET /api/defendants/{id} returns 200 for a defendant WITH at least one public event.
4.  GET /api/judges returns only judges who have at least one public reviewed event.
5.  GET /api/judges/{id} returns 404 for a judge with NO public events.
6.  GET /api/judges/{id} returns 200 for a judge WITH at least one public event.
7.  GET /api/judges response includes cl_person_id and public_event_count fields.
"""
from __future__ import annotations

from sqlalchemy import func, select

from app.db.session import SessionLocal
from app.models.entities import Defendant, Event, EventDefendant, Judge


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _first_public_defendant_id() -> int:
    """Return the DB id of the first defendant who has a public event."""
    with SessionLocal() as db:
        result = db.scalar(
            select(Defendant.id)
            .join(EventDefendant, EventDefendant.defendant_id == Defendant.id)
            .join(Event, Event.id == EventDefendant.event_id)
            .where(
                Event.public_visibility.is_(True),
                Event.review_status == "verified_court_record",
            )
            .limit(1)
        )
        assert result is not None, "Seed data must contain at least one public defendant"
        return result


def _first_public_judge_id() -> int:
    """Return the DB id of the first judge who has a public event."""
    with SessionLocal() as db:
        result = db.scalar(
            select(Judge.id)
            .join(Event, Event.judge_id == Judge.id)
            .where(
                Event.public_visibility.is_(True),
                Event.review_status == "verified_court_record",
            )
            .limit(1)
        )
        assert result is not None, "Seed data must contain at least one public judge"
        return result


def _create_isolated_defendant() -> int:
    """Insert a defendant with no event links and return its id."""
    with SessionLocal() as db:
        d = Defendant(
            anonymized_id="DEF-GATE-TEST-001",
            public_name="GateTest Isolated",
            normalized_public_name="gatetest isolated",
        )
        db.add(d)
        db.commit()
        db.refresh(d)
        return d.id


# ---------------------------------------------------------------------------
# 1. Non-existent defendant → 404
# ---------------------------------------------------------------------------

def test_defendant_nonexistent_returns_404(client):
    resp = client.get("/api/defendants/9999999")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# 2. Defendant with NO public event → 404
# ---------------------------------------------------------------------------

def test_defendant_no_public_event_returns_404(client):
    isolated_id = _create_isolated_defendant()
    resp = client.get(f"/api/defendants/{isolated_id}")
    assert resp.status_code == 404, (
        f"Expected 404 for defendant {isolated_id} with no public events, "
        f"got {resp.status_code}: {resp.text}"
    )


# ---------------------------------------------------------------------------
# 3. Defendant WITH public event → 200
# ---------------------------------------------------------------------------

def test_defendant_with_public_event_returns_200(client):
    pub_id = _first_public_defendant_id()
    resp = client.get(f"/api/defendants/{pub_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert "anonymized_id" in data
    assert data["anonymized_id"].startswith("DEF-")


# ---------------------------------------------------------------------------
# 4. Judge listing only includes judges with public events
# ---------------------------------------------------------------------------

def test_judge_list_excludes_judges_without_public_events(client):
    with SessionLocal() as db:
        total_judges = db.scalar(select(func.count(Judge.id)))
    resp = client.get("/api/judges")
    assert resp.status_code == 200
    judges = resp.json()
    # Seed has 3 judges all with public events, so list must be non-empty
    assert len(judges) >= 1
    # Every returned judge must have public_event_count > 0
    for j in judges:
        assert j["public_event_count"] > 0, (
            f"Judge {j['id']} ({j['name']}) returned with public_event_count=0"
        )


# ---------------------------------------------------------------------------
# 5. Judge with no public events → 404
# ---------------------------------------------------------------------------

def test_judge_no_public_events_returns_404(client):
    with SessionLocal() as db:
        hidden_judge = Judge(
            name="GATE TEST Hidden Judge",
            normalized_name="gate test hidden judge",
            court_id=None,
        )
        db.add(hidden_judge)
        db.commit()
        db.refresh(hidden_judge)
        hidden_id = hidden_judge.id

    resp = client.get(f"/api/judges/{hidden_id}")
    assert resp.status_code == 404, (
        f"Expected 404 for judge {hidden_id} with no public events, "
        f"got {resp.status_code}: {resp.text}"
    )


# ---------------------------------------------------------------------------
# 6. Judge WITH public event → 200
# ---------------------------------------------------------------------------

def test_judge_with_public_event_returns_200(client):
    pub_id = _first_public_judge_id()
    resp = client.get(f"/api/judges/{pub_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == pub_id
    assert data["public_event_count"] > 0


# ---------------------------------------------------------------------------
# 7. Judge list response shape includes required fields
# ---------------------------------------------------------------------------

def test_judge_list_response_shape(client):
    resp = client.get("/api/judges")
    assert resp.status_code == 200
    judges = resp.json()
    assert len(judges) >= 1
    for j in judges:
        assert "id" in j
        assert "name" in j
        assert "cl_person_id" in j          # may be None but key must exist
        assert "public_event_count" in j
        assert isinstance(j["public_event_count"], int)
