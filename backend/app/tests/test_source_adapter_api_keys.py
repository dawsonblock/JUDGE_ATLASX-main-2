"""Source adapter API-key routing regression tests.

These tests ensure parser-specific key routing stays fail-closed and never
cross-wires CanLII and Lexum credentials.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.ingestion.source_adapter_factory import (
    missing_required_secret_for_parser,
    resolve_api_key_for_parser,
)


def _settings(canlii: str | None = None, lexum: str | None = None) -> MagicMock:
    settings = MagicMock()
    settings.canlii_api_key = canlii
    settings.lexum_api_key = lexum
    return settings


def test_canlii_source_gets_only_canlii_key() -> None:
    settings = _settings(canlii="canlii-key", lexum="lexum-key")
    assert resolve_api_key_for_parser("canlii_api", settings) == "canlii-key"


def test_lexum_source_gets_only_lexum_key() -> None:
    settings = _settings(canlii="canlii-key", lexum="lexum-key")
    assert resolve_api_key_for_parser("scc_lexum_api", settings) == "lexum-key"


def test_lexum_source_does_not_get_canlii_key() -> None:
    settings = _settings(canlii="canlii-key", lexum=None)
    assert resolve_api_key_for_parser("scc_lexum_api", settings) is None


def test_canlii_source_does_not_get_lexum_key() -> None:
    settings = _settings(canlii=None, lexum="lexum-key")
    assert resolve_api_key_for_parser("canlii_api", settings) is None


def test_missing_required_key_reports_missing_secret() -> None:
    settings = _settings(canlii=None, lexum=None)
    assert missing_required_secret_for_parser("canlii_api", settings) == "JTA_CANLII_API_KEY"
    assert missing_required_secret_for_parser("scc_lexum_api", settings) == "LEXUM_API_KEY"
