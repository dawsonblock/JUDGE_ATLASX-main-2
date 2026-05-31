from app.ingestion.source_adapters import ADAPTER_REGISTRY
from app.ingestion.source_config_validator import can_run_source
from app.models.entities import SourceRegistry


def _make_runnable_source(**overrides) -> SourceRegistry:
    parser_name = next(iter(ADAPTER_REGISTRY.keys()), "dummy_parser")
    source = SourceRegistry(
        source_key="unit_test_source",
        source_name="Unit Test Source",
    )
    source.is_active = True
    source.source_class = "machine_ingest"
    source.lifecycle_state = "runnable"
    source.automation_status = "machine_ready_enabled"
    source.parser = parser_name
    source.parser_version = "1.0.0"
    source.allowed_domains = '["example.com"]'
    source.base_url = "https://example.com/feed"
    source.requires_manual_review = True
    source.public_publish_default = False
    source.source_tier = "news_only_context"

    for key, value in overrides.items():
        setattr(source, key, value)
    return source


def test_can_run_source_rejects_non_model_objects() -> None:
    runnable, blockers = can_run_source(  # type: ignore[arg-type]
        {"source_key": "not-a-model"}
    )

    assert runnable is False
    assert blockers == ["invalid_source_type"]


def test_can_run_source_accepts_fully_runnable_source() -> None:
    runnable, blockers = can_run_source(_make_runnable_source())

    assert runnable is True
    assert blockers == []


def test_can_run_source_requires_parser_version() -> None:
    runnable, blockers = can_run_source(
        _make_runnable_source(parser_version=None)
    )

    assert runnable is False
    assert "missing_parser_version" in blockers
