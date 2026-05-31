from app.ai.classify import classify_legal_record
from app.ai.redaction import redact_private_data
from app.ai.pipeline import run_ai_pipeline
from app.db.session import SessionLocal
from app.models.entities import Event, ReviewItem


def test_ai_redaction_blocks_home_address():
    result = redact_private_data("The home address is 123 Main Street.", "https://example.test/source", "news")
    assert result.privacy_risk is True
    assert result.publish_recommendation == "block"
    assert "home_address" in result.detected_risks
    assert "123 Main Street" not in result.redacted_text


def test_ai_redaction_blocks_dob():
    result = redact_private_data("DOB: 01/02/1990 appears in the source.", "https://example.test/source", "news")
    assert result.privacy_risk is True
    assert result.publish_recommendation == "block"
    assert "dob" in result.detected_risks


def test_ai_redaction_blocks_phone_and_email():
    result = redact_private_data("Call 306-555-1212 or email person@example.com.", "https://example.test/source", "news")
    assert result.privacy_risk is True
    assert result.publish_recommendation == "review_required"
    assert "phone" in result.detected_risks
    assert "email" in result.detected_risks
    assert "person@example.com" not in result.redacted_text


def test_ai_classifier_labels_release_decision_and_indicator_language():
    result = classify_legal_record("The defendant was released on conditions after the court reviewed criminal history.")
    assert result.event_type == "release_decision"
    assert result.repeat_offender_indicator is True
    assert "criminal history" in result.repeat_offender_indicators
    assert not hasattr(result, "repeat_offender_proof")


def test_ai_pipeline_creates_review_item():
    with SessionLocal() as db:
        item = run_ai_pipeline(
            db,
            {
                "record_type": "legal_event",
                "source_url": "https://example.test/court-order",
                "source_quality": "court_record",
                "text": "The court ordered release on conditions.",
                "court_id": 1,
                "case_id": 1,
                "primary_location_id": 1,
            },
        )
        db.commit()
        assert item.id is not None
        assert item.status == "pending"
        assert item.record_type == "legal_event"
        assert item.suggested_payload_json["event_type"] == "release_decision"


def test_ai_admin_review_routes_return_403_when_disabled(client):
    response = client.get("/api/admin/review/items")
    process_response = client.post("/api/admin/ai/process-source/SRC-SAMPLE-001")
    assert response.status_code == 403
    assert process_response.status_code == 403


def test_approved_review_item_can_publish_safe_event(client, monkeypatch):
    class EnabledSettings:
        enable_admin_imports = False
        enable_admin_review = True
        admin_token = "test-token"
        admin_review_token = None

    import app.auth.admin as admin_auth

    monkeypatch.setattr(admin_auth, "get_settings", lambda: EnabledSettings())
    with SessionLocal() as db:
        item = ReviewItem(
            record_type="legal_event",
            suggested_payload_json={
                "event_type": "release_decision",
                "title": "AI reviewed release order",
                "summary": "Court record indicates release on conditions.",
                "neutral_summary": "Court record indicates release on conditions.",
                "source_quote": "released on conditions",
                "court_id": 1,
                "case_id": 1,
                "primary_location_id": 1,
                "repeat_offender_indicator": False,
            },
            source_url="https://example.test/safe-order",
            source_quality="court_record",
            confidence=0.9,
            privacy_status="no_private_data_detected",
            publish_recommendation="review_required",
            status="approved",
        )
        db.add(item)
        db.commit()
        item_id = item.id

    response = client.post(f"/api/admin/review/items/{item_id}/publish", headers={"X-JTA-Admin-Token": "test-token"}, json={"actor": "test-admin"})
    assert response.status_code == 200
    event_id = response.json()["event_id"]
    with SessionLocal() as db:
        event = db.query(Event).filter_by(event_id=event_id).one()
        assert event.review_status == "pending_review"
        assert event.public_visibility is False
        assert event.event_type == "release_order"
    public_response = client.get(f"/api/events/{event_id}")
    assert public_response.status_code == 404


def test_blocked_review_item_cannot_publish(client, monkeypatch):
    class EnabledSettings:
        enable_admin_imports = False
        enable_admin_review = True
        admin_token = "test-token"
        admin_review_token = None

    import app.auth.admin as admin_auth

    monkeypatch.setattr(admin_auth, "get_settings", lambda: EnabledSettings())
    with SessionLocal() as db:
        item = ReviewItem(
            record_type="legal_event",
            suggested_payload_json={"event_type": "release_decision"},
            source_url="https://example.test/blocked",
            source_quality="news",
            confidence=0.5,
            privacy_status="privacy_risk",
            publish_recommendation="block",
            status="blocked",
        )
        db.add(item)
        db.commit()
        item_id = item.id

    response = client.post(f"/api/admin/review/items/{item_id}/publish", headers={"X-JTA-Admin-Token": "test-token"}, json={"actor": "test-admin"})
    assert response.status_code == 422


def test_ai_review_items_use_database_pagination(client, monkeypatch):
    class EnabledSettings:
        enable_admin_imports = False
        enable_admin_review = True
        admin_token = "test-token"
        admin_review_token = None

    import app.auth.admin as admin_auth

    monkeypatch.setattr(admin_auth, "get_settings", lambda: EnabledSettings())
    with SessionLocal() as db:
        for index in range(3):
            db.add(
                ReviewItem(
                    record_type="legal_event",
                    suggested_payload_json={"event_type": "release_decision", "index": index},
                    source_url=f"https://example.test/page-{index}",
                    source_quality="court_record",
                    confidence=0.8,
                    privacy_status="no_private_data_detected",
                    publish_recommendation="review_required",
                    status="pending",
                )
            )
        db.commit()

    response = client.get("/api/admin/review/items?status=pending&limit=2&offset=1", headers={"X-JTA-Admin-Token": "test-token"})
    assert response.status_code == 200
    payload = response.json()
    assert len(payload["items"]) == 2
    assert payload["total_count"] >= 3


def test_public_api_does_not_expose_private_fields_from_ai_extraction(client):
    with SessionLocal() as db:
        item = run_ai_pipeline(
            db,
            {
                "record_type": "legal_event",
                "source_url": "https://example.test/private",
                "source_quality": "news",
                "text": "DOB: 01/02/1990. The home address is 123 Main Street.",
                "court_id": 1,
                "case_id": 1,
                "primary_location_id": 1,
            },
        )
        db.commit()
        assert item.privacy_status == "privacy_risk"

    response = client.get("/api/events?limit=500")
    serialized = str(response.json()).lower()
    assert "123 main street" not in serialized
    assert "01/02/1990" not in serialized
    assert "dob" not in serialized
