from __future__ import annotations

from datetime import datetime, timezone

from app.models.entities import LegalInstrument, SourceRegistry


def _source(db_session) -> SourceRegistry:
    source = SourceRegistry(
        source_key="justice_canada_laws_xml",
        source_name="Justice Canada Laws XML",
        source_type="official",
        source_class="machine_ingest",
        lifecycle_state="runnable",
        automation_status="machine_ready_enabled",
        is_active=True,
        public_record_authority="official_legislation",
        base_url="https://laws-lois.justice.gc.ca/eng/XML/Legis.xml",
        allowed_domains='["laws-lois.justice.gc.ca"]',
        parser="laws_justice_xml",
        parser_version="justice_laws_xml_v1",
        requires_manual_review=True,
        public_publish_default=False,
        creates='["SourceSnapshot", "LegalInstrument", "LegalSection", "ReviewItem"]',
    )
    db_session.add(source)
    db_session.flush()
    return source


def test_admin_review_queue_serializes_legal_instrument_with_policy_reasons(
    client,
    db_session,
    jwt_admin_headers,
):
    source = _source(db_session)
    instrument = LegalInstrument(
        source_id=source.id,
        jurisdiction="CA-FED",
        instrument_type="act",
        unique_id="C-46",
        language="eng",
        title="Criminal Code",
        raw_snapshot_id=None,
        parser_version="justice_laws_xml_v1",
        review_status="pending_review",
        public_visibility="private",
        link_to_xml="https://laws-lois.justice.gc.ca/eng/acts/C-46/",
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(instrument)
    db_session.commit()

    response = client.get(
        "/api/admin/review-queue?entity_type=legal_instrument",
        headers=jwt_admin_headers,
    )
    assert response.status_code == 200, response.text

    payload = response.json()
    assert payload["items"], "Expected at least one legal instrument in queue"
    item = payload["items"][0]

    assert item["entity_type"] == "legal_instrument"
    assert item["id"] == instrument.id
    assert item["title"] == "Criminal Code"
    assert item["source_id"] == source.id
    assert item["jurisdiction"] == "CA-FED"
    assert item["review_status"] == "pending_review"
    assert item["public_visibility"] is False
    assert item["raw_snapshot_id"] is None
    assert item["parser_version"] == "justice_laws_xml_v1"
    assert item["created_at"] is not None
    assert isinstance(item["policy_block_reasons"], list)
    assert "missing_raw_snapshot_id" in item["policy_block_reasons"]
