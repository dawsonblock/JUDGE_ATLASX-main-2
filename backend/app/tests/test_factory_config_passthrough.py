"""Tests for source_adapter_factory.build_adapter config_json passthrough.

Verifies that:
- resource_id from config_json is forwarded to CKANApiAdapter
- Malformed config_json is ignored gracefully (no crash)
- Missing resource_id results in adapter with resource_id=None
- Non-CKAN adapters are not affected by config_json
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.ingestion.source_adapter_factory import build_adapter
from app.ingestion.source_adapters.canlii_api import CanLIIApiAdapter
from app.ingestion.source_adapters.ckan_api import CKANApiAdapter
from app.ingestion.source_adapters.scc_lexum_api import SCCLexumApiAdapter


def _make_source(
    *,
    source_key: str,
    parser: str,
    base_url: str = "https://open.canada.ca",
    config_json: str | None = None,
    source_class: str = "machine_ingest",
    allowed_domains: str = '["open.canada.ca"]',
    public_record_authority: str = "official_statistics",
) -> SimpleNamespace:
    return SimpleNamespace(
        source_key=source_key,
        parser=parser,
        base_url=base_url,
        config_json=config_json,
        source_class=source_class,
        allowed_domains=allowed_domains,
        public_record_authority=public_record_authority,
    )


def _make_settings(
    canlii_api_key: str = "",
    lexum_api_key: str = "",
) -> MagicMock:
    s = MagicMock()
    s.canlii_api_key = canlii_api_key
    s.lexum_api_key = lexum_api_key
    return s


# ---------------------------------------------------------------------------
# CKAN resource_id passthrough
# ---------------------------------------------------------------------------

def test_ckan_resource_id_forwarded_from_config_json():
    rid = "6271ad46-4a0d-4748-8e1a-2c5d21d2bfcd"
    source = _make_source(
        source_key="canada_open_data_crime",
        parser="ckan_api",
        config_json=json.dumps({"resource_id": rid}),
    )
    adapter = build_adapter(source, _make_settings())
    assert isinstance(adapter, CKANApiAdapter)
    assert adapter._resource_id == rid


def test_ckan_no_resource_id_when_config_json_absent():
    source = _make_source(
        source_key="canada_open_data_crime",
        parser="ckan_api",
        config_json=None,
    )
    adapter = build_adapter(source, _make_settings())
    assert isinstance(adapter, CKANApiAdapter)
    assert adapter._resource_id is None


def test_ckan_no_resource_id_when_config_json_empty_object():
    source = _make_source(
        source_key="canada_open_data_crime",
        parser="ckan_api",
        config_json="{}",
    )
    adapter = build_adapter(source, _make_settings())
    assert isinstance(adapter, CKANApiAdapter)
    assert adapter._resource_id is None


def test_ckan_malformed_config_json_does_not_raise():
    source = _make_source(
        source_key="canada_open_data_crime",
        parser="ckan_api",
        config_json="not-valid-json{{",
    )
    # Should not raise — malformed config is silently ignored
    adapter = build_adapter(source, _make_settings())
    assert isinstance(adapter, CKANApiAdapter)
    assert adapter._resource_id is None


def test_ckan_api_url_includes_resource_id_when_set():
    rid = "abc-123"
    source = _make_source(
        source_key="saskatoon_open_data_portal",
        parser="ckan_api",
        base_url="https://data.saskatoon.ca",
        config_json=json.dumps({"resource_id": rid}),
    )
    adapter = build_adapter(source, _make_settings())
    assert isinstance(adapter, CKANApiAdapter)
    url = adapter._ckan_api_url()
    assert f"resource_id={rid}" in url


def test_ckan_pagination_settings_forwarded_from_config_json() -> None:
    source = _make_source(
        source_key="canada_open_data_crime",
        parser="ckan_api",
        config_json=json.dumps(
            {
                "resource_id": "rid-123",
                "page_limit": 25,
                "max_pages": 4,
                "offset": 50,
            }
        ),
    )

    adapter = build_adapter(source, _make_settings())
    assert isinstance(adapter, CKANApiAdapter)
    assert adapter._resource_id == "rid-123"
    assert adapter._page_limit == 25
    assert adapter._max_pages == 4
    assert adapter._offset == 50


def test_canlii_adapter_uses_only_canlii_key() -> None:
    source = _make_source(
        source_key="sk_courts_qb_decisions",
        parser="canlii_api",
        config_json=json.dumps({"databases": ["skkb"]}),
    )
    adapter = build_adapter(
        source,
        _make_settings(canlii_api_key="canlii-secret", lexum_api_key="lexum-secret"),
    )
    assert isinstance(adapter, CanLIIApiAdapter)
    assert adapter._api_key == "canlii-secret"


def test_lexum_adapter_uses_only_lexum_key() -> None:
    source = _make_source(
        source_key="scc_decisions",
        parser="scc_lexum_api",
        base_url="https://decisions.scc-csc.ca",
    )
    adapter = build_adapter(
        source,
        _make_settings(canlii_api_key="canlii-secret", lexum_api_key="lexum-secret"),
    )
    assert isinstance(adapter, SCCLexumApiAdapter)
    assert adapter._api_key == "lexum-secret"


# ---------------------------------------------------------------------------
# Guard: non-machine_ingest sources are rejected
# ---------------------------------------------------------------------------

def test_portal_reference_source_is_rejected_by_factory():
    source = _make_source(
        source_key="canada_open_data_crime",
        parser="ckan_api",
        source_class="portal_reference",
    )
    with pytest.raises(ValueError, match="portal_reference"):
        build_adapter(source, _make_settings())
