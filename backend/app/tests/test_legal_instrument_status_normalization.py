from __future__ import annotations

from datetime import datetime, timezone

from app.ingestion.adapters import (
    CreatedLegalInstrument,
    CreatedReviewItem,
    IngestionResult,
)
from app.ingestion.source_runner import persist_ingestion_result
from app.models.entities import IngestionRun, LegalInstrument, ReviewItem, SourceRegistry


def _source(db_session):
    existing = (
        db_session.query(SourceRegistry)
        .filter(SourceRegistry.source_key == "justice_canada_laws_xml")
        .first()
    )
    if existing is not None:
        existing.source_class = "machine_ingest"
        existing.lifecycle_state = "runnable"
        existing.automation_status = "machine_ready_enabled"
        existing.is_active = True
        existing.public_record_authority = "official_legislation"
        existing.base_url = "https://laws-lois.justice.gc.ca/eng/XML/Legis.xml"
        existing.allowed_domains = '["laws-lois.justice.gc.ca"]'
        existing.parser = "laws_justice_xml"
        existing.parser_version = "justice_laws_xml_v1"
        existing.requires_manual_review = True
        existing.public_publish_default = False
        existing.creates = '["SourceSnapshot", "LegalInstrument", "LegalSection", "ReviewItem"]'
        db_session.flush()
        return existing

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


def _run(db_session, source_id: str) -> IngestionRun:
    run = IngestionRun(
        source_name=source_id,
        started_at=datetime.now(timezone.utc),
        status="running",
    )
    db_session.add(run)
    db_session.flush()
    return run


def test_persist_sets_legal_instrument_pending_review_and_review_item_pending(db_session):
    source = _source(db_session)
    run = _run(db_session, source.source_key)

    result = IngestionResult(
        source_key=source.source_key,
        parser_version=source.parser_version,
        raw_snapshot_bytes=b"<Legis>fixture</Legis>",
        fetch_http_status=200,
        fetch_content_type="application/xml",
        fetch_url=source.base_url,
        legal_instruments=[
            CreatedLegalInstrument(
                source_key=source.source_key,
                instrument_type="act",
                unique_id="C-46",
                language="eng",
                title="Criminal Code",
                payload={
                    "jurisdiction": "CA-FED",
                    "instrument_type": "act",
                    "parser_version": "justice_laws_xml_v1",
                },
                sections=[
                    {
                        "section_label": "1",
                        "text": "This is a test section",
                    }
                ],
                source_url="https://laws-lois.justice.gc.ca/eng/acts/C-46/",
            )
        ],
        review_items=[
            CreatedReviewItem(
                source_key=source.source_key,
                headline="Criminal Code",
                url="https://laws-lois.justice.gc.ca/eng/acts/C-46/",
                extracted_text="Test extract",
                confidence_score=0.9,
                payload={
                    "record_type": "LegalInstrument",
                    "source_key": source.source_key,
                    "unique_id": "C-46",
                    "language": "eng",
                    "instrument_type": "act",
                },
            )
        ],
    )

    summary = persist_ingestion_result(db_session, source, run, result)
    assert summary.persisted_legal_instruments == 1
    assert summary.persisted_review_items == 1

    instrument = (
        db_session.query(LegalInstrument)
        .filter(
            LegalInstrument.source_id == source.id,
            LegalInstrument.unique_id == "C-46",
            LegalInstrument.language == "eng",
        )
        .one()
    )
    review_item = next(
        (
            row
            for row in db_session.query(ReviewItem)
            .filter(ReviewItem.record_type == "LegalInstrument")
            .all()
            if row.suggested_payload_json.get("source_key") == source.source_key
            and row.suggested_payload_json.get("unique_id") == "C-46"
            and row.suggested_payload_json.get("language") == "eng"
        ),
        None,
    )
    assert review_item is not None

    assert instrument.review_status == "pending_review"
    assert instrument.public_visibility == "private"
    assert review_item.status == "pending"

    pending_legacy = (
        db_session.query(LegalInstrument)
        .filter(LegalInstrument.review_status == "pending")
        .count()
    )
    assert pending_legacy == 0
