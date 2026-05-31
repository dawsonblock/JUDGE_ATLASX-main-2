"""Unit tests for source_verifier_v1.

Uses monkeypatching to mock HTTP fetch and Ollama calls — no real network
requests or Ollama installation required.

Proves:
1.  Returns status='disabled' when ollama_enabled=False (default).
2.  Returns status='fetch_failed' when URL fetch fails.
3.  Returns status='empty_source' when extracted text is empty.
4.  Returns status='model_failed' when Ollama returns None.
5.  Returns status='parse_failed' when model output is not valid JSON.
6.  Returns status='ok' with findings for a valid mocked response.
7.  Forbidden scoring keys are stripped from findings.
8.  HTML is stripped from fetched content before passing to Ollama.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.services.source_fetcher import FetchResult
from app.services.source_verifier import (
    _parse_findings,
    _sanitize_finding,
    _strip_html,
    verify_source,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _MockSettings:
    ollama_enabled: bool = True
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "mistral"
    ollama_timeout_seconds: int = 5


_CLAIMED = {
    "event_type": "detention_order",
    "decision_date": "2024-01-15",
    "decision_result": "detained",
    "summary": "Order of detention under 18 U.S.C. § 3142.",
}

_VALID_FINDINGS_JSON = (
    '[{"field": "event_type", "claim": "detention_order", '
    '"supported": true, "evidence_excerpt": "order of detention", '
    '"severity": "ok"}]'
)


# ---------------------------------------------------------------------------
# 1. Disabled when ollama_enabled=False
# ---------------------------------------------------------------------------

def test_verify_source_disabled_by_default():
    result = verify_source("event", 1, "https://example.com/doc", _CLAIMED)
    assert result.status == "disabled"
    assert result.findings == []


# ---------------------------------------------------------------------------
# 2. fetch_failed when URL cannot be fetched
# ---------------------------------------------------------------------------

def _make_fetch_result(text: str | None, error: str | None = None) -> FetchResult:
    """Create a mock FetchResult for testing."""
    from datetime import datetime, timezone
    return FetchResult(
        url="https://example.com/doc",
        final_url="https://example.com/doc",
        fetched_at=datetime.now(timezone.utc),
        http_status=200 if text else None,
        content_type="text/html",
        headers={},
        raw_content=text.encode() if text else None,
        raw_content_hash=None,
        extracted_text=text,
        extracted_text_hash=None,
        error=error,
        snapshot_id=1,
    )


def test_verify_source_fetch_failed(monkeypatch):
    monkeypatch.setattr(
        "app.services.source_verifier.get_settings",
        lambda: _MockSettings(),
    )
    def _mock_fetch(url, **kwargs):
        return _make_fetch_result(None, error="Fetch failed")

    monkeypatch.setattr(
        "app.services.source_verifier.fetch_source",
        _mock_fetch,
    )
    result = verify_source("event", 1, "https://example.com/doc", _CLAIMED)
    assert result.status == "fetch_failed"
    assert result.findings == []


# ---------------------------------------------------------------------------
# 3. empty_source when text extraction yields nothing
# ---------------------------------------------------------------------------

def test_verify_source_empty_source(monkeypatch):
    monkeypatch.setattr(
        "app.services.source_verifier.get_settings",
        lambda: _MockSettings(),
    )
    def _mock_fetch_empty(url, **kwargs):
        return _make_fetch_result("")

    monkeypatch.setattr(
        "app.services.source_verifier.fetch_source",
        _mock_fetch_empty,
    )
    result = verify_source("event", 1, "https://example.com/doc", _CLAIMED)
    assert result.status == "empty_source"
    assert result.findings == []


# ---------------------------------------------------------------------------
# 4. model_failed when Ollama returns None
# ---------------------------------------------------------------------------

def test_verify_source_model_failed(monkeypatch):
    monkeypatch.setattr(
        "app.services.source_verifier.get_settings",
        lambda: _MockSettings(),
    )
    def _mock_fetch_detention(url, **kwargs):
        return _make_fetch_result(
            "The court issued an order of detention on January 15."
        )

    monkeypatch.setattr(
        "app.services.source_verifier.fetch_source",
        _mock_fetch_detention,
    )
    monkeypatch.setattr(
        "app.services.source_verifier._call_ollama",
        lambda prompt, model, base_url, timeout: None,
    )
    result = verify_source("event", 1, "https://example.com/doc", _CLAIMED)
    assert result.status == "model_failed"
    assert result.findings == []


# ---------------------------------------------------------------------------
# 5. parse_failed when model output is not parseable JSON
# ---------------------------------------------------------------------------

def test_verify_source_parse_failed(monkeypatch):
    monkeypatch.setattr(
        "app.services.source_verifier.get_settings",
        lambda: _MockSettings(),
    )
    def _mock_fetch_court(url, **kwargs):
        return _make_fetch_result("Court text about detention.")

    monkeypatch.setattr(
        "app.services.source_verifier.fetch_source",
        _mock_fetch_court,
    )
    monkeypatch.setattr(
        "app.services.source_verifier._call_ollama",
        lambda prompt, model, base_url, timeout: "Sure! The fields look supported.",
    )
    result = verify_source("event", 1, "https://example.com/doc", _CLAIMED)
    assert result.status == "parse_failed"
    assert result.findings == []


# ---------------------------------------------------------------------------
# 6. ok with field-level findings for valid mocked response
# ---------------------------------------------------------------------------

def test_verify_source_ok(monkeypatch):
    monkeypatch.setattr(
        "app.services.source_verifier.get_settings",
        lambda: _MockSettings(),
    )
    def _mock_fetch_order(url, **kwargs):
        return _make_fetch_result(
            "The court entered an order of detention on January 15, 2024."
        )

    monkeypatch.setattr(
        "app.services.source_verifier.fetch_source",
        _mock_fetch_order,
    )
    monkeypatch.setattr(
        "app.services.source_verifier._call_ollama",
        lambda prompt, model, base_url, timeout: _VALID_FINDINGS_JSON,
    )
    result = verify_source("event", 1, "https://example.com/doc", _CLAIMED)
    assert result.status == "ok"
    assert len(result.findings) == 1
    f = result.findings[0]
    assert f["field"] == "event_type"
    assert f["supported"] is True
    assert f["severity"] == "ok"


# ---------------------------------------------------------------------------
# 7. Forbidden scoring keys are stripped
# ---------------------------------------------------------------------------

def test_sanitize_finding_strips_forbidden_keys():
    dirty = {
        "field": "event_type",
        "claim": "detention_order",
        "supported": True,
        "evidence_excerpt": "order of detention",
        "severity": "ok",
        "guilt_score": 0.95,
        "danger_score": 0.8,
        "judge_score": 7,
        "defendant_score": 100,
        "risk_score": 0.5,
    }
    clean = _sanitize_finding(dirty)
    assert "guilt_score" not in clean
    assert "danger_score" not in clean
    assert "judge_score" not in clean
    assert "defendant_score" not in clean
    assert "risk_score" not in clean
    assert clean["field"] == "event_type"
    assert clean["supported"] is True


def test_verify_source_ok_strips_forbidden_keys(monkeypatch):
    monkeypatch.setattr(
        "app.services.source_verifier.get_settings",
        lambda: _MockSettings(),
    )
    def _mock_fetch_text(url, **kwargs):
        return _make_fetch_result("Detention order text.")

    monkeypatch.setattr(
        "app.services.source_verifier.fetch_source",
        _mock_fetch_text,
    )
    monkeypatch.setattr(
        "app.services.source_verifier._call_ollama",
        lambda prompt, model, base_url, timeout: (
            '[{"field": "event_type", "claim": "detention_order", '
            '"supported": true, "evidence_excerpt": null, '
            '"severity": "ok", "guilt_score": 0.99}]'
        ),
    )
    result = verify_source("event", 1, "https://example.com/doc", _CLAIMED)
    assert result.status == "ok"
    assert "guilt_score" not in result.findings[0]


# ---------------------------------------------------------------------------
# 8. HTML stripping
# ---------------------------------------------------------------------------

def test_strip_html_removes_script_and_tags():
    html = (
        "<html><head><title>Ignore</title></head>"
        "<body><script>alert(1)</script>"
        "<p>Order of detention issued.</p>"
        "<nav>Nav links</nav>"
        "</body></html>"
    )
    text = _strip_html(html)
    assert "Order of detention issued." in text
    assert "alert" not in text
    assert "<p>" not in text


# ---------------------------------------------------------------------------
# _parse_findings edge cases
# ---------------------------------------------------------------------------

def test_parse_findings_direct_array():
    result = _parse_findings('[{"field": "x", "supported": true}]')
    assert result is not None
    assert result[0]["field"] == "x"


def test_parse_findings_embedded_array():
    result = _parse_findings(
        'Here are the findings: [{"field": "y", "supported": false}] Done.'
    )
    assert result is not None
    assert result[0]["field"] == "y"


def test_parse_findings_invalid_returns_none():
    assert _parse_findings("Not JSON at all.") is None
    assert _parse_findings('{"key": "value"}') is None  # object, not array
