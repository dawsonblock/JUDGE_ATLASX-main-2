from datetime import datetime, timezone

from app.ingestion.adapters import CreatedRecord, IngestionResult
from app.ingestion.source_runner import _validate_machine_ingest_contract
from app.models.entities import SourceRegistry


def _source() -> SourceRegistry:
    return SourceRegistry(
        source_key="test_source",
        source_name="Test Source",
        source_class="machine_ingest",
        is_active=True,
        parser="test_parser",
        parser_version="v1",
        base_url="https://example.com",
    )


def test_machine_ingest_blocks_adapter_direct_publication_flags() -> None:
    source = _source()
    result = IngestionResult(
        source_key="test_source",
        parser_version="v1",
        fetch_url="https://example.com/feed",
        raw_snapshot_bytes=b"snapshot",
        created_records=[
            CreatedRecord(
                source_key="test_source",
                record_type="CrimeIncident",
                external_id="x-1",
                payload={"is_public": True},
            )
        ],
    )

    reasons = _validate_machine_ingest_contract(result, source)
    assert "adapter_attempted_direct_publication" in reasons


def test_machine_ingest_blocks_disabled_source() -> None:
    source = _source()
    source.is_active = False
    result = IngestionResult(
        source_key="test_source",
        parser_version="v1",
        fetch_url="https://example.com/feed",
        raw_snapshot_bytes=b"snapshot",
    )

    reasons = _validate_machine_ingest_contract(result, source)
    assert "source_disabled" in reasons


def test_machine_ingest_requires_fetch_url_and_raw_snapshot() -> None:
    source = _source()
    source.base_url = None
    result = IngestionResult(
        source_key="test_source",
        parser_version="v1",
        fetch_url=None,
        raw_snapshot_bytes=None,
    )

    reasons = _validate_machine_ingest_contract(result, source)
    assert "no_fetch_url" in reasons
    assert "no_raw_content" in reasons
