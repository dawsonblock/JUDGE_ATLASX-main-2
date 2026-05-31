from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.ingestion.source_adapter_factory import (
    build_adapter,
    missing_required_secret_for_parser,
)


class _Settings(SimpleNamespace):
    canlii_api_key: str | None = None
    lexum_api_key: str | None = None


def _source(**overrides):
    base = {
        "source_key": "test_source",
        "parser": "laws_justice_xml",
        "base_url": "https://laws-lois.justice.gc.ca/eng/XML/Legis.xml",
        "allowed_domains": '["laws-lois.justice.gc.ca"]',
        "public_record_authority": "official_legislation",
        "config_json": "{}",
        "source_class": "machine_ingest",
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_build_adapter_requires_machine_ingest_class() -> None:
    source = _source(source_class="portal_reference")
    with pytest.raises(ValueError):
        build_adapter(source, _Settings())


def test_build_adapter_returns_none_for_unknown_parser() -> None:
    source = _source(parser="missing_parser")
    adapter = build_adapter(source, _Settings())
    assert adapter is None


def test_canlii_secret_is_required_when_missing() -> None:
    missing = missing_required_secret_for_parser("canlii_api", _Settings())
    assert missing == "JTA_CANLII_API_KEY"
