"""Adapter-level source-runner contract tests.

Covers integration contracts that are complementary to
test_parser_version_contract.py (which tests _validate_machine_ingest_contract
in isolation) and test_run_persist_summary_truth.py (which tests summary
field defaults and source_key_mismatch quarantine).

Focus here:
1. Adapter modules expose a PARSER_VERSION constant matching the YAML.
2. _MACHINE_INGEST_CLASSES gate is wired to the right source_class values.
3. persist_ingestion_result quarantines when the machine_ingest contract fails.
4. Non-machine-ingest sources (portal_reference) bypass the contract gate.
"""

from __future__ import annotations

import pathlib
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import yaml
import pytest

# ── YAML fixture ─────────────────────────────────────────────────────────────

_SOURCES_YAML = (
    pathlib.Path(__file__).resolve().parents[1]
    / "ingestion"
    / "sources"
    / "canada_saskatchewan_sources.yaml"
)


def _load_yaml_source(source_key: str) -> dict:
    data = yaml.safe_load(_SOURCES_YAML.read_text())
    for entry in data["sources"]:
        if entry.get("source_key") == source_key:
            return entry
    raise KeyError(f"source_key {source_key!r} not found in YAML")


# ── helpers ───────────────────────────────────────────────────────────────────


def _make_db() -> MagicMock:
    db = MagicMock()
    db.add = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = None
    return db


def _make_run() -> MagicMock:
    run = MagicMock()
    run.id = 1
    run.persisted_count = 0
    run.skipped_count = 0
    return run


# ── PARSER_VERSION constant tests ─────────────────────────────────────────────


def test_federal_court_html_has_parser_version_constant() -> None:
    """federal_court_html adapter must declare a PARSER_VERSION constant."""
    from app.ingestion.source_adapters import federal_court_html

    assert hasattr(federal_court_html, "PARSER_VERSION"), (
        "federal_court_html module must define PARSER_VERSION"
    )
    assert isinstance(federal_court_html.PARSER_VERSION, str)
    assert federal_court_html.PARSER_VERSION != ""


def test_laws_justice_xml_has_parser_version_constant() -> None:
    """laws_justice_xml adapter must declare a PARSER_VERSION constant."""
    from app.ingestion.source_adapters import laws_justice_xml

    assert hasattr(laws_justice_xml, "PARSER_VERSION"), (
        "laws_justice_xml module must define PARSER_VERSION"
    )
    assert isinstance(laws_justice_xml.PARSER_VERSION, str)
    assert laws_justice_xml.PARSER_VERSION != ""


def test_federal_court_html_parser_version_matches_yaml() -> None:
    """Adapter constant must equal the YAML parser_version for federal_court_canada."""
    from app.ingestion.source_adapters import federal_court_html

    yaml_entry = _load_yaml_source("federal_court_canada")
    assert federal_court_html.PARSER_VERSION == yaml_entry["parser_version"], (
        "federal_court_html.PARSER_VERSION must match "
        f"YAML parser_version (got {federal_court_html.PARSER_VERSION!r}, "
        f"yaml has {yaml_entry['parser_version']!r})"
    )


def test_laws_justice_xml_parser_version_matches_yaml() -> None:
    """Adapter constant must equal the YAML parser_version for justice_canada_laws_xml."""
    from app.ingestion.source_adapters import laws_justice_xml

    yaml_entry = _load_yaml_source("justice_canada_laws_xml")
    assert laws_justice_xml.PARSER_VERSION == yaml_entry["parser_version"], (
        "laws_justice_xml.PARSER_VERSION must match "
        f"YAML parser_version (got {laws_justice_xml.PARSER_VERSION!r}, "
        f"yaml has {yaml_entry['parser_version']!r})"
    )


# ── _MACHINE_INGEST_CLASSES gate ──────────────────────────────────────────────


def test_machine_ingest_classes_contains_machine_ingest() -> None:
    from app.ingestion.source_runner import _MACHINE_INGEST_CLASSES

    assert "machine_ingest" in _MACHINE_INGEST_CLASSES


def test_machine_ingest_classes_contains_none() -> None:
    """Legacy sources (source_class=None) must still be gated."""
    from app.ingestion.source_runner import _MACHINE_INGEST_CLASSES

    assert None in _MACHINE_INGEST_CLASSES


# ── persist_ingestion_result quarantine integration ───────────────────────────


def test_persist_quarantines_machine_ingest_with_no_parser_version() -> None:
    """machine_ingest source with no parser_version on source → quarantined_count=1."""
    from app.ingestion import source_runner
    from app.ingestion.adapters import IngestionResult

    db = _make_db()
    run = _make_run()

    source = MagicMock()
    source.source_key = "test_adapter"
    source.source_class = "machine_ingest"
    source.parser_version = None  # not set → contract violation
    source.base_url = "https://example.gc.ca/"

    result = IngestionResult(
        source_key="test_adapter",
        raw_snapshot_bytes=b"<html>data</html>",
        fetch_url="https://example.gc.ca/data",
        fetch_http_status=200,
        fetch_content_type="text/html",
        parser_version="1.0",
        created_records=[],
        review_items=[],
        errors=[],
    )

    with patch.object(source_runner, "quarantine_run") as mock_quarantine:
        summary = source_runner.persist_ingestion_result(db, source, run, result)

    mock_quarantine.assert_called_once()
    assert summary.quarantined_count == 1
    assert "no_parser_version" in summary.contract_violations


def test_persist_quarantines_machine_ingest_with_version_mismatch() -> None:
    """machine_ingest source whose parser_version disagrees with adapter → quarantined."""
    from app.ingestion import source_runner
    from app.ingestion.adapters import IngestionResult

    db = _make_db()
    run = _make_run()

    source = MagicMock()
    source.source_key = "test_adapter"
    source.source_class = "machine_ingest"
    source.parser_version = "1.0"
    source.base_url = "https://example.gc.ca/"

    result = IngestionResult(
        source_key="test_adapter",
        raw_snapshot_bytes=b"<html>data</html>",
        fetch_url="https://example.gc.ca/data",
        fetch_http_status=200,
        fetch_content_type="text/html",
        parser_version="2.0",  # mismatch
        created_records=[],
        review_items=[],
        errors=[],
    )

    with patch.object(source_runner, "quarantine_run") as mock_quarantine:
        summary = source_runner.persist_ingestion_result(db, source, run, result)

    mock_quarantine.assert_called_once()
    assert summary.quarantined_count == 1
    assert "parser_version_mismatch" in summary.contract_violations


def test_non_machine_ingest_source_bypasses_contract_gate() -> None:
    """portal_reference source is not auto-ingested; contract gate must not fire."""
    from app.ingestion import source_runner
    from app.ingestion.adapters import IngestionResult

    db = _make_db()
    run = _make_run()

    source = MagicMock()
    source.source_key = "portal_src"
    source.source_class = "portal_reference"
    source.parser_version = None  # no version — would fail machine_ingest gate
    source.base_url = "https://example.gc.ca/"
    source.creates = '["SourceSnapshot"]'
    source.public_record_authority = "portal_reference"

    result = IngestionResult(
        source_key="portal_src",
        raw_snapshot_bytes=b"",
        fetch_url=None,
        fetch_http_status=None,
        fetch_content_type=None,
        parser_version=None,
        created_records=[],
        review_items=[],
        errors=[],
    )

    with patch.object(source_runner, "quarantine_run") as mock_quarantine:
        # No raw bytes and no records → early return (no quarantine, not a contract issue)
        summary = source_runner.persist_ingestion_result(db, source, run, result)

    mock_quarantine.assert_not_called()
    assert summary.quarantined_count == 0
