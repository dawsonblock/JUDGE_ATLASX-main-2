"""Phase 4 Justice Canada XML end-to-end ingestion tests."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

from app.ingestion.fetcher import FetchCallable
from app.ingestion.source_adapters.laws_justice_xml import LawsJusticeXmlAdapter
from app.ingestion.source_runner import persist_ingestion_result
from app.models.entities import (
    CrimeIncident,
    IngestionRun,
    LegalInstrument,
    LegalSection,
    ReviewItem,
    SourceRegistry,
    SourceSnapshot,
)
from app.review.decisions import record_decision
from app.review.publication_gate import (
    PublicationBlockedError,
    assert_legal_instrument_publication_ready,
)
from app.services.evidence_chat import chat_about_evidence
from app.services.snapshot_writer import read_snapshot_content
from app.services.source_fetcher import FetchResult

_FIXTURES = Path(__file__).parent / "fixtures" / "sources"


def _fetcher_from_fixtures() -> FetchCallable:
    legis = (_FIXTURES / "legis_sample.xml").read_bytes()
    statute = (_FIXTURES / "c-46_sample.xml").read_bytes()

    def _fetcher(target_url: str, allowed_domains=(), *, params=None, **kw) -> FetchResult:
        content = legis if target_url.endswith("Legis.xml") else statute
        return FetchResult(
            url=target_url,
            final_url=target_url,
            fetched_at=datetime.now(timezone.utc),
            http_status=200,
            content_type="application/xml",
            headers={"content-type": "application/xml"},
            raw_content=content,
            raw_content_hash=None,
            extracted_text=None,
            extracted_text_hash=None,
            error=None,
        )

    return _fetcher


def _make_adapter(fetcher: FetchCallable | None = None) -> LawsJusticeXmlAdapter:
    return LawsJusticeXmlAdapter(
        source_key="justice_canada_laws_xml",
        base_url="https://laws-lois.justice.gc.ca/eng/XML/Legis.xml",
        allowed_domains_json='["laws-lois.justice.gc.ca", "lois-laws.justice.gc.ca"]',
        public_record_authority="official_legislation",
        fetcher=fetcher or _fetcher_from_fixtures(),
    )


def _make_source(db_session, *, source_key: str = "justice_canada_laws_xml") -> SourceRegistry:
    existing = db_session.query(SourceRegistry).filter_by(source_key=source_key).first()
    if existing is not None:
        existing.parser = "laws_justice_xml"
        existing.parser_version = "justice_laws_xml_v1"
        existing.source_class = "machine_ingest"
        existing.base_url = "https://laws-lois.justice.gc.ca/eng/XML/Legis.xml"
        existing.allowed_domains = '["laws-lois.justice.gc.ca", "lois-laws.justice.gc.ca"]'
        existing.public_record_authority = "official_legislation"
        existing.creates = '["LegalInstrument", "LegalSection", "ReviewItem", "SourceSnapshot"]'
        existing.is_active = True
        db_session.flush()
        return existing

    source = SourceRegistry(
        source_key=source_key,
        source_name="Justice Canada Consolidated Acts and Regulations XML",
        source_type="aggregate_stats",
        source_tier="official_government_statistics",
        license="Open Government Licence - Canada",
        fetch_method="xml",
        update_cadence="monthly",
        precision_level="national",
        auto_publish_enabled=False,
        requires_manual_review=True,
        parser_version="justice_laws_xml_v1",
        automation_status="machine_ready_disabled",
        is_active=True,
        jurisdiction="Canada",
        category="legislation",
        priority=4,
        enabled_default=False,
        public_record_authority="official_legislation",
        base_url="https://laws-lois.justice.gc.ca/eng/XML/Legis.xml",
        allowed_domains='["laws-lois.justice.gc.ca", "lois-laws.justice.gc.ca"]',
        parser="laws_justice_xml",
        creates='["LegalInstrument", "LegalSection", "ReviewItem", "SourceSnapshot"]',
        public_publish_default=False,
        terms_url="https://laws-lois.justice.gc.ca/eng/licence.html",
        source_class="machine_ingest",
    )
    db_session.add(source)
    db_session.flush()
    return source


def _make_run(db_session) -> IngestionRun:
    run = IngestionRun(
        source_name="justice_canada_laws_xml",
        started_at=datetime.now(timezone.utc),
        status="running",
    )
    db_session.add(run)
    db_session.flush()
    return run


def test_xml_adapter_returns_review_items_and_legal_instruments() -> None:
    result = _make_adapter().run()

    assert result.success is True
    assert result.parser_version == "justice_laws_xml_v1"
    assert result.raw_snapshot_bytes
    assert result.fetch_http_status == 200
    assert result.fetch_content_type == "application/xml"
    assert result.fetch_url
    assert len(result.legal_instruments) == 2
    assert len(result.review_items) == 2
    assert result.created_records == []
    assert {item.payload["language"] for item in result.review_items} == {"eng", "fra"}


def test_xml_adapter_schema_drift_fails_closed() -> None:
    def bad_fetcher(target_url: str, allowed_domains=(), *, params=None, **kw) -> FetchResult:
        return FetchResult(
            url=target_url,
            final_url=target_url,
            fetched_at=datetime.now(timezone.utc),
            http_status=200,
            content_type="application/xml",
            headers={},
            raw_content=b"<BadRoot />",
            raw_content_hash=None,
            extracted_text=None,
            extracted_text_hash=None,
            error=None,
        )

    result = _make_adapter(fetcher=bad_fetcher).run()

    assert result.success is False
    assert result.review_items == []
    assert result.legal_instruments == []
    assert result.created_records == []
    assert result.raw_snapshot_bytes is None


def test_persist_xml_result_writes_snapshot_legal_rows_and_review_items(db_session) -> None:
    source = _make_source(db_session)
    run = _make_run(db_session)
    result = _make_adapter().run()

    summary = persist_ingestion_result(db_session, source, run, result)
    db_session.flush()

    assert summary.snapshots_written == 1
    assert summary.persisted_legal_instruments == 2
    assert summary.persisted_review_items == 2
    assert db_session.query(CrimeIncident).filter_by(source_name=source.source_key).count() == 0
    assert db_session.query(SourceSnapshot).filter_by(source_key=source.source_key).count() >= 1

    eng = (
        db_session.query(LegalInstrument)
        .filter_by(source_id=source.id, unique_id="C-46", language="eng")
        .one()
    )
    assert eng.review_status == "pending_review"
    assert eng.public_visibility == "private"
    assert eng.raw_snapshot_id is not None
    assert db_session.query(LegalSection).filter_by(legal_instrument_id=eng.id).count() == 2
    assert db_session.query(ReviewItem).filter_by(record_type="LegalInstrument").count() >= 2


def test_persist_xml_result_dedupes_legal_instruments_and_sections(db_session) -> None:
    source = _make_source(db_session)
    first_run = _make_run(db_session)
    first_result = _make_adapter().run()
    persist_ingestion_result(db_session, source, first_run, first_result)
    db_session.flush()

    second_run = _make_run(db_session)
    second_result = _make_adapter().run()
    persist_ingestion_result(db_session, source, second_run, second_result)
    db_session.flush()

    instruments = db_session.query(LegalInstrument).filter_by(source_id=source.id).all()
    assert {(i.unique_id, i.language) for i in instruments} == {
        ("C-46", "eng"),
        ("C-46", "fra"),
    }
    section_count = (
        db_session.query(LegalSection)
        .join(LegalInstrument)
        .filter(LegalInstrument.source_id == source.id)
        .count()
    )
    assert section_count == 4


def test_persist_xml_result_quarantines_parser_version_mismatch(db_session) -> None:
    source = _make_source(db_session)
    source.parser_version = "unexpected_parser_v9"
    run = _make_run(db_session)
    result = _make_adapter().run()

    summary = persist_ingestion_result(db_session, source, run, result)
    db_session.flush()

    assert summary.quarantined_count == 1
    assert "parser_version_mismatch" in summary.contract_violations
    assert summary.persisted_legal_instruments == 0
    assert (
        db_session.query(LegalInstrument)
        .filter_by(source_id=source.id, unique_id="C-46", language="eng")
        .count()
        == 0
    )


def test_snapshot_hash_round_trip_matches_stored_hash(db_session) -> None:
    source = _make_source(db_session)
    run = _make_run(db_session)
    result = _make_adapter().run()

    summary = persist_ingestion_result(db_session, source, run, result)
    db_session.flush()

    assert summary.snapshots_written == 1
    snapshot = (
        db_session.query(SourceSnapshot)
        .filter_by(source_key=source.source_key, ingestion_run_id=run.id)
        .order_by(SourceSnapshot.id.desc())
        .first()
    )
    assert snapshot is not None
    content = read_snapshot_content(db_session, snapshot)
    assert content is not None
    assert hashlib.sha256(content).hexdigest() == snapshot.original_content_hash


def test_legal_publication_gate_and_chat_require_approval(db_session) -> None:
    source = _make_source(db_session)
    run = _make_run(db_session)
    result = _make_adapter().run()
    persist_ingestion_result(db_session, source, run, result)
    db_session.flush()

    instrument = (
        db_session.query(LegalInstrument)
        .filter_by(source_id=source.id, unique_id="C-46", language="eng")
        .one()
    )
    try:
        assert_legal_instrument_publication_ready(instrument)
    except PublicationBlockedError:
        pass
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("pending legal instrument should not publish")

    pending_chat = chat_about_evidence(db_session, "Criminal Code section 1")
    assert pending_chat.legal_context_citations == []

    item = next(
        (
            row
            for row in db_session.query(ReviewItem)
            .filter(ReviewItem.record_type == "LegalInstrument")
            .all()
            if row.suggested_payload_json.get("unique_id") == "C-46"
            and row.suggested_payload_json.get("language") == "eng"
        ),
        None,
    )
    assert item is not None
    decision = record_decision(
        db_session,
        item.id,
        decision="approved",
        reviewer_id="phase4-test",
        notes="approved legal context",
    )
    assert decision.ok is True
    db_session.flush()
    db_session.refresh(instrument)

    try:
        assert_legal_instrument_publication_ready(instrument)
    except PublicationBlockedError:
        pass
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("ReviewItem approval must not publish legal instruments")

    approved_chat = chat_about_evidence(db_session, "Criminal Code section 1")
    assert approved_chat.legal_context_citations == []
    assert approved_chat.citations == []
