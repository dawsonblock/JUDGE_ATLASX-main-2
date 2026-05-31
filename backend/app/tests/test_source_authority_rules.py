from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from app.ingestion.adapters import (
    CreatedLegalInstrument,
    CreatedRecord,
    CreatedReviewItem,
    IngestionResult,
)
from app.ingestion.source_runner import persist_ingestion_result
from app.models.entities import IngestionRun, LegalInstrument, SourceRegistry, SourceSnapshot


def _source(db_session) -> SourceRegistry:
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


def _run(db_session, source_key: str) -> IngestionRun:
    run = IngestionRun(
        source_name=source_key,
        started_at=datetime.now(timezone.utc),
        status="running",
    )
    db_session.add(run)
    db_session.flush()
    return run


def test_justice_xml_can_persist_legal_path_types(db_session):
    source = _source(db_session)
    run = _run(db_session, source.source_key)
    snapshots_before = db_session.query(SourceSnapshot).count()
    legal_before = db_session.query(LegalInstrument).count()
    unique_id = f"AUTH-{uuid4().hex[:8]}"

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
                unique_id=unique_id,
                language="eng",
                title="Criminal Code",
                payload={"jurisdiction": "CA-FED", "instrument_type": "act"},
                sections=[{"section_label": "1", "text": "section text"}],
                source_url="https://laws-lois.justice.gc.ca/eng/acts/C-46/",
            )
        ],
        review_items=[
            CreatedReviewItem(
                source_key=source.source_key,
                headline="Criminal Code",
                url="https://laws-lois.justice.gc.ca/eng/acts/C-46/",
                extracted_text="section text",
                confidence_score=0.95,
                payload={
                    "record_type": "LegalInstrument",
                    "source_key": source.source_key,
                        "unique_id": unique_id,
                    "language": "eng",
                },
            )
        ],
    )

    summary = persist_ingestion_result(db_session, source, run, result)
    assert summary.quarantined_count == 0
    assert summary.persisted_legal_instruments == 1
    assert summary.persisted_review_items == 1
    assert db_session.query(SourceSnapshot).count() == snapshots_before + 1
    assert db_session.query(LegalInstrument).count() == legal_before + 1
    assert (
        db_session.query(LegalInstrument)
        .filter(
            LegalInstrument.unique_id == unique_id,
            LegalInstrument.language == "eng",
        )
        .count()
        >= 1
    )


def test_justice_xml_cannot_emit_crime_incident(db_session):
    source = _source(db_session)
    run = _run(db_session, source.source_key)
    snapshots_before = db_session.query(SourceSnapshot).count()

    result = IngestionResult(
        source_key=source.source_key,
        parser_version=source.parser_version,
        raw_snapshot_bytes=b"<Legis>fixture</Legis>",
        fetch_http_status=200,
        fetch_content_type="application/xml",
        fetch_url=source.base_url,
        created_records=[
            CreatedRecord(
                source_key=source.source_key,
                record_type="CrimeIncident",
                external_id="forbidden",
                payload={"incident_type": "test", "incident_category": "test"},
                source_url="https://example.test/forbidden",
            )
        ],
    )

    summary = persist_ingestion_result(db_session, source, run, result)
    assert summary.quarantined_count == 1
    assert summary.persisted_incidents == 0
    assert summary.contract_violations
    assert any("CrimeIncident" in msg for msg in summary.contract_violations)
    assert db_session.query(SourceSnapshot).count() == snapshots_before
