"""Saskatoon public-safety staging tests at ingestion-matrix path."""

from __future__ import annotations

import json
from pathlib import Path


def _sources_file() -> Path:
    return (
        Path(__file__).resolve().parents[2]
        / "ingestion"
        / "sources"
        / "canada_saskatchewan_sources.yaml"
    )


def test_saskatoon_public_safety_registry_state_honest() -> None:
    import yaml  # type: ignore

    payload = yaml.safe_load(_sources_file().read_text(encoding="utf-8"))
    entry = next(
        s
        for s in payload.get("sources", [])
        if s.get("source_key") == "saskatoon_open_data_public_safety"
    )

    assert entry["parser"] == "ckan_api"
    assert entry["automation_status"] == "machine_ready_enabled"
    assert entry["lifecycle_state"] == "runnable"
    assert entry["enabled_default"] is False
    assert entry["requires_manual_review"] is True
    assert entry["public_publish_default"] is False


def test_saskatoon_ckan_fixtures_exist() -> None:
    fixture_dir = Path(__file__).resolve().parents[1] / "fixtures"
    page1 = fixture_dir / "saskatoon_public_safety_ckan_page1.json"
    page2 = fixture_dir / "saskatoon_public_safety_ckan_page2.json"

    assert page1.exists()
    assert page2.exists()

    for page in (page1, page2):
        payload = json.loads(page.read_text(encoding="utf-8"))
        assert payload.get("success") is True
        assert isinstance(payload.get("result", {}).get("records", []), list)
