"""Phase 1 Justice Canada XML hardening contracts."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.auth.jwt_handler import create_access_token
from app.ingestion.source_adapter_factory import parse_laws_xml_target_ids
from app.main import app
from app.db.session import SessionLocal
from app.models.entities import SourceRegistry


client = TestClient(app)


def _headers() -> dict[str, str]:
    token = create_access_token(email="admin@example.com", role="admin")
    return {"Authorization": f"Bearer {token}"}


def test_parse_laws_xml_target_ids_accepts_multiple_ids() -> None:
    parsed = parse_laws_xml_target_ids("C-46, SOR-2002-227")
    assert parsed == ["C-46", "SOR-2002-227"]


def test_parse_laws_xml_target_ids_rejects_malformed_values() -> None:
    with pytest.raises(ValueError, match="Malformed law target IDs"):
        parse_laws_xml_target_ids("C-46, BAD ID")


def test_factory_rejects_invalid_laws_target_ids(monkeypatch) -> None:
    from app.ingestion.source_adapter_factory import build_adapter

    source = SimpleNamespace(
        source_key="justice_canada_laws_xml",
        parser="laws_justice_xml",
        source_class="machine_ingest",
        base_url="https://laws-lois.justice.gc.ca/eng/XML/Legis.xml",
        allowed_domains='["laws-lois.justice.gc.ca"]',
        public_record_authority="official_legislation",
        config_json=None,
    )
    settings = SimpleNamespace(
        canlii_api_key=None,
        lexum_api_key=None,
        laws_xml_target_ids="C-46, BAD ID",
    )

    adapter = build_adapter(source, settings)
    assert adapter is None


def test_run_source_rejects_inactive_source() -> None:
    source_key = "test_inactive_justice_source"
    with SessionLocal() as db:
        db.query(SourceRegistry).filter(SourceRegistry.source_key == source_key).delete()
        db.add(
            SourceRegistry(
                source_key=source_key,
                source_name="Inactive Justice Source",
                source_type="legislation",
                source_class="machine_ingest",
                parser="laws_justice_xml",
                parser_version="justice_laws_xml_v1",
                automation_status="machine_ready_enabled",
                base_url="https://laws-lois.justice.gc.ca/eng/XML/Legis.xml",
                allowed_domains='["laws-lois.justice.gc.ca"]',
                public_record_authority="official_legislation",
                terms_url="https://laws-lois.justice.gc.ca/eng/licence.html",
                requires_manual_review=True,
                public_publish_default=False,
                is_active=False,
            )
        )
        db.commit()

    response = client.post(
        f"/api/admin/sources/{source_key}/run",
        headers=_headers(),
    )
    assert response.status_code == 409
    assert "is disabled" in response.json()["detail"]

    with SessionLocal() as db:
        db.query(SourceRegistry).filter(SourceRegistry.source_key == source_key).delete()
        db.commit()
