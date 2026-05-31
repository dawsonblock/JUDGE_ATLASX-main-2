"""Tests for machine_ingest adapter evidence snapshot contract.

Every machine_ingest adapter that returns items must:
- Populate result.raw_snapshot_bytes (non-empty bytes)
- Populate result.fetch_http_status
- Populate result.fetch_content_type
- Populate result.fetch_url
- Include source_url on every review item / created record

These tests use local HTML/XML fixtures to avoid network calls.
Fixtures are validated against live site structure (2026-05-06).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.ingestion.fetcher import FetchCallable
from app.services.source_fetcher import FetchResult

_FIXTURES = Path(__file__).parent / "fixtures" / "sources"


def _make_mock_fetcher(
    fixture_name: str,
    status_code: int = 200,
    content_type: str = "text/html",
    url: str = "https://example.gc.ca/",
) -> FetchCallable:
    """Build a mock fetcher callable from a fixture file."""
    content = (_FIXTURES / fixture_name).read_bytes()

    def _fetcher(target_url: str, allowed_domains=(), *, params=None, **kw) -> FetchResult:
        return FetchResult(
            url=target_url,
            final_url=url,
            fetched_at=datetime.now(timezone.utc),
            http_status=status_code,
            content_type=content_type,
            headers={"content-type": content_type},
            raw_content=content,
            raw_content_hash=None,
            extracted_text=None,
            extracted_text_hash=None,
            error=None,
        )

    return _fetcher


# ── CanLIIApiAdapter (SK courts) ─────────────────────────────────────────────


class TestCanLIIApiAdapterSKContract:
    def _make_adapter(self, fetcher: FetchCallable | None = None) -> object:
        from app.ingestion.source_adapters.canlii_api import CanLIIApiAdapter

        return CanLIIApiAdapter(
            source_key="sk_courts_qb_decisions",
            base_url="https://api.canlii.org/v1",
            api_key="fake-api-key",
            databases=["skkb"],
            result_count=10,
            allowed_domains_json='["api.canlii.org", "canlii.org", "www.canlii.org"]',
            public_record_authority="official_court_record",
            fetcher=fetcher,
        )

    def test_run_with_fixture_returns_raw_snapshot_bytes(self) -> None:
        mock_fetcher = _make_mock_fetcher(
            "sk_courts_qb_decisions/sample.json",
            content_type="application/json",
            url="https://api.canlii.org/v1/caseBrowse/en/skkb/",
        )
        adapter = self._make_adapter(fetcher=mock_fetcher)
        result = adapter.run()
        assert result.raw_snapshot_bytes is not None
        assert len(result.raw_snapshot_bytes) > 0

    def test_run_with_fixture_sets_fetch_metadata(self) -> None:
        mock_fetcher = _make_mock_fetcher(
            "sk_courts_qb_decisions/sample.json",
            content_type="application/json",
            url="https://api.canlii.org/v1/caseBrowse/en/skkb/",
        )
        adapter = self._make_adapter(fetcher=mock_fetcher)
        result = adapter.run()
        assert result.fetch_http_status == 200
        assert result.fetch_content_type is not None
        assert result.fetch_url is not None

    def test_run_with_fixture_extracts_canlii_links(self) -> None:
        mock_fetcher = _make_mock_fetcher(
            "sk_courts_qb_decisions/sample.json",
            content_type="application/json",
            url="https://api.canlii.org/v1/caseBrowse/en/skkb/",
        )
        adapter = self._make_adapter(fetcher=mock_fetcher)
        result = adapter.run()
        assert result.records_fetched == 2

    def test_parse_fixture_items_have_source_url(self) -> None:
        from app.ingestion.source_adapters.canlii_api import CanLIIApiAdapter

        adapter = CanLIIApiAdapter(
            source_key="sk_courts_qb_decisions",
            base_url="https://api.canlii.org/v1",
            api_key="fake-api-key",
            databases=["skkb"],
            result_count=10,
            allowed_domains_json='["api.canlii.org", "canlii.org", "www.canlii.org"]',
            public_record_authority="official_court_record",
        )
        import json as _json

        raw_payload = _json.loads((_FIXTURES / "sk_courts_qb_decisions/sample.json").read_text())
        raw = raw_payload["cases"]
        parsed = adapter.parse(raw)
        assert len(parsed) == 2
        for item in parsed:
            assert item.source_url, "Every parsed record must have source_url"
            assert item.payload.get("headline"), "Every parsed record must have headline"

    def test_parse_fixture_items_have_allowed_host(self) -> None:
        from app.ingestion.source_adapters.canlii_api import CanLIIApiAdapter

        adapter = CanLIIApiAdapter(
            source_key="sk_courts_qb_decisions",
            base_url="https://api.canlii.org/v1",
            api_key="fake-api-key",
            databases=["skkb"],
            result_count=10,
            allowed_domains_json='["api.canlii.org", "canlii.org", "www.canlii.org"]',
            public_record_authority="official_court_record",
        )
        import json as _json

        raw_payload = _json.loads((_FIXTURES / "sk_courts_qb_decisions/sample.json").read_text())
        raw = raw_payload["cases"]
        parsed = adapter.parse(raw)
        for record in parsed:
            assert record.source_url, "source_url must be non-empty"
            assert "canlii.org" in record.source_url, "source_url must resolve to CanLII"


# ── FederalCourtHtmlAdapter ───────────────────────────────────────────────────


class TestFederalCourtHtmlAdapterContract:
    def _make_adapter(self, fetcher: FetchCallable | None = None) -> object:
        from app.ingestion.source_adapters.federal_court_html import FederalCourtHtmlAdapter

        return FederalCourtHtmlAdapter(
            source_key="federal_court_canada",
            base_url="https://decisions.fct-cf.gc.ca/fc-cf/en/0/ann.do?iframe=true",
            allowed_domains_json='["decisions.fct-cf.gc.ca", "fct-cf.gc.ca", "www.fct-cf.gc.ca"]',
            public_record_authority="official_court_record",
            fetcher=fetcher,
        )

    def test_run_with_fixture_returns_raw_snapshot_bytes(self) -> None:
        mock_fetcher = _make_mock_fetcher(
            "federal_court_index.html",
            url="https://decisions.fct-cf.gc.ca/fc-cf/en/0/ann.do?iframe=true",
        )
        adapter = self._make_adapter(fetcher=mock_fetcher)
        result = adapter.run()
        assert result.raw_snapshot_bytes is not None
        assert len(result.raw_snapshot_bytes) > 0

    def test_run_with_fixture_sets_fetch_metadata(self) -> None:
        mock_fetcher = _make_mock_fetcher(
            "federal_court_index.html",
            url="https://decisions.fct-cf.gc.ca/fc-cf/en/0/ann.do?iframe=true",
        )
        adapter = self._make_adapter(fetcher=mock_fetcher)
        result = adapter.run()
        assert result.fetch_http_status == 200
        assert result.fetch_content_type is not None
        assert result.fetch_url is not None

    def test_parse_fixture_extracts_expected_count(self) -> None:
        from app.ingestion.source_adapters.federal_court_html import FederalCourtHtmlAdapter

        adapter = FederalCourtHtmlAdapter(
            source_key="federal_court_canada",
            base_url="https://decisions.fct-cf.gc.ca/fc-cf/en/0/ann.do?iframe=true",
            allowed_domains_json='["decisions.fct-cf.gc.ca", "fct-cf.gc.ca", "www.fct-cf.gc.ca"]',
            public_record_authority="official_court_record",
        )
        html = (_FIXTURES / "federal_court_index.html").read_text()
        raw = adapter._parse_items(html)
        assert len(raw) == 3, f"Expected 3 items from fixture, got {len(raw)}"

    def test_parse_fixture_items_have_non_empty_headline(self) -> None:
        from app.ingestion.source_adapters.federal_court_html import FederalCourtHtmlAdapter

        adapter = FederalCourtHtmlAdapter(
            source_key="federal_court_canada",
            base_url="https://decisions.fct-cf.gc.ca/fc-cf/en/0/ann.do?iframe=true",
            allowed_domains_json='["decisions.fct-cf.gc.ca", "fct-cf.gc.ca", "www.fct-cf.gc.ca"]',
            public_record_authority="official_court_record",
        )
        html = (_FIXTURES / "federal_court_index.html").read_text()
        raw = adapter._parse_items(html)
        for item in raw:
            assert item.get("headline"), "headline must be non-empty"
            assert item.get("url"), "url must be non-empty"
            assert "decisions.fct-cf.gc.ca" in item["url"], "url must be absolute"

    def test_parse_fixture_extracts_neutral_citation(self) -> None:
        from app.ingestion.source_adapters.federal_court_html import FederalCourtHtmlAdapter

        adapter = FederalCourtHtmlAdapter(
            source_key="federal_court_canada",
            base_url="https://decisions.fct-cf.gc.ca/fc-cf/en/0/ann.do?iframe=true",
            allowed_domains_json='["decisions.fct-cf.gc.ca", "fct-cf.gc.ca", "www.fct-cf.gc.ca"]',
            public_record_authority="official_court_record",
        )
        html = (_FIXTURES / "federal_court_index.html").read_text()
        raw = adapter._parse_items(html)
        # At least one item should have a neutral citation from the h3
        citations = [item.get("neutral_citation") for item in raw if item.get("neutral_citation")]
        assert len(citations) > 0, "At least one item should have a neutral citation"


# ── LawsJusticeHtmlAdapter ────────────────────────────────────────────────────


class TestLawsJusticeHtmlAdapterContract:
    def _make_adapter(self, fetcher: FetchCallable | None = None) -> object:
        from app.ingestion.source_adapters.laws_justice_html import LawsJusticeHtmlAdapter

        return LawsJusticeHtmlAdapter(
            source_key="justice_canada_laws_xml",
            base_url="https://laws-lois.justice.gc.ca/eng/acts/C-46/",
            allowed_domains_json='["laws-lois.justice.gc.ca", "lois-laws.justice.gc.ca"]',
            public_record_authority="official_legislation",
            fetcher=fetcher,
        )

    def test_run_with_fixture_returns_raw_snapshot_bytes(self) -> None:
        mock_fetcher = _make_mock_fetcher(
            "laws_justice_page.html",
            url="https://laws-lois.justice.gc.ca/eng/acts/C-46/",
        )
        adapter = self._make_adapter(fetcher=mock_fetcher)
        result = adapter.run()
        assert result.raw_snapshot_bytes is not None
        assert len(result.raw_snapshot_bytes) > 0

    def test_parse_fixture_extracts_amendments_from_table(self) -> None:
        from app.ingestion.source_adapters.laws_justice_html import LawsJusticeHtmlAdapter

        adapter = LawsJusticeHtmlAdapter(
            source_key="justice_canada_laws_xml",
            base_url="https://laws-lois.justice.gc.ca/eng/acts/C-46/",
            allowed_domains_json='["laws-lois.justice.gc.ca", "lois-laws.justice.gc.ca"]',
            public_record_authority="official_legislation",
        )
        html = (_FIXTURES / "laws_justice_page.html").read_text()
        raw = adapter._parse_amendments(html)
        assert len(raw) == 5, f"Expected 5 amendments from fixture, got {len(raw)}"

    def test_parse_fixture_items_have_non_empty_headline(self) -> None:
        from app.ingestion.source_adapters.laws_justice_html import LawsJusticeHtmlAdapter

        adapter = LawsJusticeHtmlAdapter(
            source_key="justice_canada_laws_xml",
            base_url="https://laws-lois.justice.gc.ca/eng/acts/C-46/",
            allowed_domains_json='["laws-lois.justice.gc.ca", "lois-laws.justice.gc.ca"]',
            public_record_authority="official_legislation",
        )
        html = (_FIXTURES / "laws_justice_page.html").read_text()
        raw = adapter._parse_amendments(html)
        for item in raw:
            assert item.get("headline"), "headline must be non-empty"
            assert item.get("url"), "url must be non-empty"
            assert item.get("date"), "date must be non-empty for amendments table"

    def test_parse_fixture_items_have_absolute_urls(self) -> None:
        from app.ingestion.source_adapters.laws_justice_html import LawsJusticeHtmlAdapter

        adapter = LawsJusticeHtmlAdapter(
            source_key="justice_canada_laws_xml",
            base_url="https://laws-lois.justice.gc.ca/eng/acts/C-46/",
            allowed_domains_json='["laws-lois.justice.gc.ca", "lois-laws.justice.gc.ca"]',
            public_record_authority="official_legislation",
        )
        html = (_FIXTURES / "laws_justice_page.html").read_text()
        raw = adapter._parse_amendments(html)
        for item in raw:
            assert item["url"].startswith("https://"), f"URL must be absolute: {item['url']}"


# ── SKLegislatureHtmlAdapter ─────────────────────────────────────────────────


class TestSKLegislatureHtmlAdapterContract:
    def _make_adapter(self, fetcher: FetchCallable | None = None) -> object:
        from app.ingestion.source_adapters.sk_legislature_html import SKLegislatureHtmlAdapter

        return SKLegislatureHtmlAdapter(
            source_key="sk_legislature_hansard",
            base_url="https://www.legassembly.sk.ca/legislative-business/debates-hansard/",
            allowed_domains_json='["legassembly.sk.ca", "www.legassembly.sk.ca", "docs.legassembly.sk.ca"]',
            public_record_authority="official_legislation",
            fetcher=fetcher,
        )

    def test_run_with_fixture_returns_raw_snapshot_bytes(self) -> None:
        mock_fetcher = _make_mock_fetcher(
            "sk_legislature_hansard.html",
            url="https://www.legassembly.sk.ca/legislative-business/debates-hansard/",
        )
        adapter = self._make_adapter(fetcher=mock_fetcher)
        result = adapter.run()
        assert result.raw_snapshot_bytes is not None
        assert len(result.raw_snapshot_bytes) > 0

    def test_run_with_fixture_sets_fetch_metadata(self) -> None:
        mock_fetcher = _make_mock_fetcher(
            "sk_legislature_hansard.html",
            url="https://www.legassembly.sk.ca/legislative-business/debates-hansard/",
        )
        adapter = self._make_adapter(fetcher=mock_fetcher)
        result = adapter.run()
        assert result.fetch_http_status == 200
        assert result.fetch_content_type is not None
        assert result.fetch_url is not None

    def test_parse_fixture_extracts_expected_count(self) -> None:
        from app.ingestion.source_adapters.sk_legislature_html import SKLegislatureHtmlAdapter

        adapter = SKLegislatureHtmlAdapter(
            source_key="sk_legislature_hansard",
            base_url="https://www.legassembly.sk.ca/legislative-business/debates-hansard/",
            allowed_domains_json='["legassembly.sk.ca", "www.legassembly.sk.ca", "docs.legassembly.sk.ca"]',
            public_record_authority="official_legislation",
        )
        html = (_FIXTURES / "sk_legislature_hansard.html").read_text()
        raw = adapter._parse_hansard_index(html)
        # 3 legislatures × 2 indexes (subject + speaker) = 6 items
        assert len(raw) == 6, f"Expected 6 items from fixture, got {len(raw)}"

    def test_parse_fixture_items_have_source_url(self) -> None:
        from app.ingestion.source_adapters.sk_legislature_html import SKLegislatureHtmlAdapter

        adapter = SKLegislatureHtmlAdapter(
            source_key="sk_legislature_hansard",
            base_url="https://www.legassembly.sk.ca/legislative-business/debates-hansard/",
            allowed_domains_json='["legassembly.sk.ca", "www.legassembly.sk.ca", "docs.legassembly.sk.ca"]',
            public_record_authority="official_legislation",
        )
        html = (_FIXTURES / "sk_legislature_hansard.html").read_text()
        raw = adapter._parse_hansard_index(html)
        for item in raw:
            assert item.get("url"), "url must be non-empty"
            assert item.get("headline"), "headline must be non-empty"
            assert "docs.legassembly.sk.ca" in item["url"] or "legassembly.sk.ca" in item["url"]

    def test_parse_fixture_items_have_legislature_metadata(self) -> None:
        from app.ingestion.source_adapters.sk_legislature_html import SKLegislatureHtmlAdapter

        adapter = SKLegislatureHtmlAdapter(
            source_key="sk_legislature_hansard",
            base_url="https://www.legassembly.sk.ca/legislative-business/debates-hansard/",
            allowed_domains_json='["legassembly.sk.ca", "www.legassembly.sk.ca", "docs.legassembly.sk.ca"]',
            public_record_authority="official_legislation",
        )
        html = (_FIXTURES / "sk_legislature_hansard.html").read_text()
        raw = adapter._parse_hansard_index(html)
        for item in raw:
            assert item.get("legislature"), "legislature must be non-empty"
            assert item.get("index_type") in ("subject", "speaker")


# ── SCCLexumApiAdapter ────────────────────────────────────────────────────────


class TestSCCLexumApiAdapterContract:
    def _make_adapter(self, fetcher: FetchCallable | None = None) -> object:
        from app.ingestion.source_adapters.scc_lexum_api import SCCLexumApiAdapter

        return SCCLexumApiAdapter(
            source_key="scc_decisions",
            base_url="https://decisions.scc-csc.ca/scc-csc/scc-csc/en/rss.do",
            allowed_domains_json='["decisions.scc-csc.ca", "scc-csc.ca", "lexum.com"]',
            public_record_authority="official_court_record",
            fetcher=fetcher,
        )

    def test_run_with_fixture_returns_raw_snapshot_bytes(self) -> None:
        mock_fetcher = _make_mock_fetcher(
            "scc_feed.xml",
            content_type="application/rss+xml",
            url="https://decisions.scc-csc.ca/scc-csc/scc-csc/en/rss.do",
        )
        adapter = self._make_adapter(fetcher=mock_fetcher)
        result = adapter.run()
        assert result.raw_snapshot_bytes is not None
        assert len(result.raw_snapshot_bytes) > 0

    def test_run_with_fixture_sets_fetch_metadata(self) -> None:
        mock_fetcher = _make_mock_fetcher(
            "scc_feed.xml",
            content_type="application/rss+xml",
            url="https://decisions.scc-csc.ca/scc-csc/scc-csc/en/rss.do",
        )
        adapter = self._make_adapter(fetcher=mock_fetcher)
        result = adapter.run()
        assert result.fetch_http_status == 200
        assert result.fetch_content_type is not None
        assert result.fetch_url is not None

    def test_parse_fixture_extracts_expected_count(self) -> None:
        from app.ingestion.source_adapters.scc_lexum_api import SCCLexumApiAdapter
        import xml.etree.ElementTree as ET

        adapter = SCCLexumApiAdapter(
            source_key="scc_decisions",
            base_url="https://decisions.scc-csc.ca/scc-csc/scc-csc/en/rss.do",
            allowed_domains_json='["decisions.scc-csc.ca", "scc-csc.ca", "lexum.com"]',
            public_record_authority="official_court_record",
        )
        xml_content = (_FIXTURES / "scc_feed.xml").read_text()
        root = ET.fromstring(xml_content)
        raw = []
        for item in root.iter("item"):
            entry: dict = {}
            for child in item:
                tag = child.tag.split("}")[-1]
                entry[tag] = child.text
            raw.append(entry)
        assert len(raw) == 3, f"Expected 3 items from fixture, got {len(raw)}"
        parsed = adapter.parse(raw)
        assert len(parsed) == 3

    def test_parse_fixture_items_have_source_url(self) -> None:
        from app.ingestion.source_adapters.scc_lexum_api import SCCLexumApiAdapter
        import xml.etree.ElementTree as ET

        adapter = SCCLexumApiAdapter(
            source_key="scc_decisions",
            base_url="https://decisions.scc-csc.ca/scc-csc/scc-csc/en/rss.do",
            allowed_domains_json='["decisions.scc-csc.ca", "scc-csc.ca", "lexum.com"]',
            public_record_authority="official_court_record",
        )
        xml_content = (_FIXTURES / "scc_feed.xml").read_text()
        root = ET.fromstring(xml_content)
        raw = []
        for item in root.iter("item"):
            entry: dict = {}
            for child in item:
                tag = child.tag.split("}")[-1]
                entry[tag] = child.text
            raw.append(entry)
        parsed = adapter.parse(raw)
        for record in parsed:
            assert record.source_url, "source_url must be non-empty"
            assert record.payload.get("headline"), "headline must be non-empty"

    def test_parse_fixture_extracts_neutral_citation(self) -> None:
        from app.ingestion.source_adapters.scc_lexum_api import SCCLexumApiAdapter
        import xml.etree.ElementTree as ET

        adapter = SCCLexumApiAdapter(
            source_key="scc_decisions",
            base_url="https://decisions.scc-csc.ca/scc-csc/scc-csc/en/rss.do",
            allowed_domains_json='["decisions.scc-csc.ca", "scc-csc.ca", "lexum.com"]',
            public_record_authority="official_court_record",
        )
        xml_content = (_FIXTURES / "scc_feed.xml").read_text()
        root = ET.fromstring(xml_content)
        raw = []
        for item in root.iter("item"):
            entry: dict = {}
            for child in item:
                tag = child.tag.split("}")[-1]
                entry[tag] = child.text
            raw.append(entry)
        parsed = adapter.parse(raw)
        # All items in fixture have neutral citations
        for record in parsed:
            assert record.payload.get("neutral_citation"), "neutral_citation must be extracted"
            assert record.payload.get("published_at"), "published_at must be extracted from date field"
