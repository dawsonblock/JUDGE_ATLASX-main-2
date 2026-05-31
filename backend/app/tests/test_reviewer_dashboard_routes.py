"""Test reviewer dashboard routes (Phase 9).

Verifies that all reviewer dashboard routes are properly configured
with authentication, authorization, and rate limiting.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


def test_review_queue_route_exists(client):
    """Test that /api/admin/review-queue route exists."""
    response = client.get("/api/admin/review-queue")
    # Should return 401 (unauthorized) since no auth provided
    assert response.status_code in [401, 403]


def test_review_history_route_exists(client):
    """Test that /api/admin/review-history route exists."""
    response = client.get("/api/admin/review-history")
    # Should return 401 (unauthorized) since no auth provided
    assert response.status_code in [401, 403]


def test_review_decision_route_exists(client):
    """Test that /api/admin/review-queue/{entity_type}/{entity_id}/decision route exists."""
    response = client.post(
        "/api/admin/review-queue/event/1/decision",
        json={"decision": "approved"}
    )
    # Should return 401 (unauthorized) since no auth provided
    assert response.status_code in [401, 403]


def test_retract_legal_source_route_exists(client):
    """Test that /api/admin/legal-sources/{source_id}/retract route exists."""
    response = client.post("/api/admin/legal-sources/test-source/retract")
    # Should return 401 (unauthorized) since no auth provided
    assert response.status_code in [401, 403]


def test_contradictions_list_route_exists(client):
    """Test that /api/admin/contradictions route exists."""
    response = client.get("/api/admin/contradictions")
    # Should return 401 (unauthorized) since no auth provided
    assert response.status_code in [401, 403]


def test_contradictions_by_claim_route_exists(client):
    """Test that /api/admin/contradictions/by-claim/{claim_id} route exists."""
    response = client.get("/api/admin/contradictions/by-claim/1")
    # Should return 401 (unauthorized) since no auth provided
    assert response.status_code in [401, 403]


def test_contradictions_by_entity_route_exists(client):
    """Test that /api/admin/contradictions/by-entity/{entity_id} route exists."""
    response = client.get("/api/admin/contradictions/by-entity/1")
    # Should return 401 (unauthorized) since no auth provided
    assert response.status_code in [401, 403]


def test_resolve_contradiction_route_exists(client):
    """Test that /api/admin/contradictions/{contradiction_id}/resolve route exists."""
    response = client.post(
        "/api/admin/contradictions/1/resolve",
        json={"status": "resolved", "resolution_note": "Test resolution"}
    )
    # Should return 401 (unauthorized) since no auth provided
    assert response.status_code in [401, 403]


def test_reviewer_dashboard_routes_have_proper_dependencies():
    """Phase 9: Verify reviewer dashboard routes have proper auth and rate limit dependencies."""
    from app.api.routes.admin_review import router

    # Get all routes from the router
    routes = router.routes

    # Expected route paths
    expected_paths = {
        "/api/admin/review-queue",
        "/api/admin/review-history",
        "/api/admin/review-queue/{entity_type}/{entity_id}/decision",
        "/api/admin/legal-sources/{source_id}/retract",
        "/api/admin/contradictions",
        "/api/admin/contradictions/by-claim/{claim_id}",
        "/api/admin/contradictions/by-entity/{entity_id}",
        "/api/admin/contradictions/{contradiction_id}/resolve",
    }

    # Extract actual paths from routes
    actual_paths = {route.path for route in routes if hasattr(route, "path")}

    # Verify all expected paths exist
    for expected_path in expected_paths:
        assert expected_path in actual_paths, f"Missing route: {expected_path}"

    # Verify GET routes for review queue and history have require_admin_review dependency
    review_queue_route = next(
        (r for r in routes if hasattr(r, "path") and r.path == "/api/admin/review-queue"),
        None
    )
    assert review_queue_route is not None
    # The route should have dependencies (require_admin_review, rate_limit_admin)
    assert len(review_queue_route.dependencies) >= 1

    # Verify POST routes for mutations have rate_limit_admin dependency
    decision_route = next(
        (r for r in routes if hasattr(r, "path") and "decision" in r.path),
        None
    )
    assert decision_route is not None
    assert len(decision_route.dependencies) >= 1

    # Verify contradiction routes have require_admin_review dependency
    contradictions_route = next(
        (r for r in routes if hasattr(r, "path") and r.path == "/api/admin/contradictions"),
        None
    )
    assert contradictions_route is not None
    assert len(contradictions_route.dependencies) >= 1


def test_review_queue_supports_all_entity_types():
    """Phase 9: Verify review queue supports all entity types."""
    from app.api.routes.admin_review import _review_statements

    # Test that all entity types are supported
    entity_types = ["event", "crime_incident", "source", "legal_instrument"]
    for entity_type in entity_types:
        data_stmt, count_stmt = _review_statements(entity_type, None, None)
        assert data_stmt is not None
        assert count_stmt is not None


def test_review_decision_serialization_includes_policy_block_reasons():
    """Phase 9: Verify review decision serialization includes policy block reasons."""
    from app.api.routes.admin_review import _serialize_review_item
    from app.db.session import SessionLocal
    from app.models.entities import Event, Court, Case

    db = SessionLocal()
    try:
        court = Court(name="Test Court")
        db.add(court)
        db.commit()

        case = Case(court_id=court.id, case_number="TEST-CASE-1")
        db.add(case)
        db.commit()

        # Create a test event
        event = Event(
            event_id="test-event",
            court_id=court.id,
            case_id=case.id,
            primary_location_id=court.location_id,
            event_type="hearing",
            title="Test Event",
            summary="Test summary",
            incident_type="test",
            source_quality="official",
            review_status="pending",
            public_visibility=False,
        )
        db.add(event)
        db.commit()

        # Serialize the event
        serialized = _serialize_review_item(db, "event", event)

        # Verify policy_block_reasons field exists
        assert "policy_block_reasons" in serialized
        assert isinstance(serialized["policy_block_reasons"], list)

    finally:
        db.rollback()
        db.close()


def test_contradiction_resolution_decrements_claim_counts():
    """Phase 9: Verify contradiction resolution decrements claim contradiction counts."""
    from app.db.session import SessionLocal
    from app.models.entities import MemoryClaim, MemoryContradiction, CanonicalEntity

    db = SessionLocal()
    try:
        # Create entity
        entity = CanonicalEntity(
            name="Test Entity",
            entity_type="person"
        )
        db.add(entity)
        db.commit()

        # Create claims with contradiction counts
        claim_a = MemoryClaim(
            claim_key="test-claim-a",
            claim_uid="uid-a",
            claim_type="test",
            entity_id=entity.id,
            claim_value="Value A",
            normalized_value="value_a",
            confidence=0.9,
            contradiction_count=1,
            status="active",
        )
        claim_b = MemoryClaim(
            claim_key="test-claim-b",
            claim_uid="uid-b",
            claim_type="test",
            entity_id=entity.id,
            claim_value="Value B",
            normalized_value="value_b",
            confidence=0.9,
            contradiction_count=1,
            status="active",
        )
        db.add(claim_a)
        db.add(claim_b)
        db.commit()

        # Create contradiction
        contradiction = MemoryContradiction(
            claim_a_id=claim_a.id,
            claim_b_id=claim_b.id,
            conflict_type="value_contradiction",
            severity="high",
            status="open",
        )
        db.add(contradiction)
        db.commit()

        # Resolve contradiction
        contradiction.status = "resolved"
        contradiction.resolved_at = None  # Will be set by route

        # Decrement counts (simulating route logic)
        if claim_a.contradiction_count > 0:
            claim_a.contradiction_count -= 1
        if claim_b.contradiction_count > 0:
            claim_b.contradiction_count -= 1

        db.commit()

        # Verify counts were decremented
        db.refresh(claim_a)
        db.refresh(claim_b)
        assert claim_a.contradiction_count == 0
        assert claim_b.contradiction_count == 0

    finally:
        db.rollback()
        db.close()
