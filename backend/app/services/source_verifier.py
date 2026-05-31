"""Source-grounded correctness verifier — source_verifier_v1.

Fetches the source URL for a record, extracts text, and calls a local Ollama
model to check whether the claimed event_type, date, location, status, and
summary are supported by the source text.

Design constraints:
- Field-level findings only.  No guilt scores, danger scores, judge scores,
  or defendant scores are produced or stored.
- Fails closed: if the URL cannot be fetched or the model response cannot be
  parsed, the check is marked failed and no findings are written.
- Enabled only when JTA_OLLAMA_ENABLED=true.  Off by default so the service
  can run without Ollama present.
- Uses stdlib html.parser to strip HTML — no extra dependencies.
- Uses source_fetcher for HTTP fetching with SSRF protection and snapshot
  persistence for provenance.
"""
from __future__ import annotations

import json
import logging
import re
import urllib.request
from dataclasses import dataclass, field
from html.parser import HTMLParser
from typing import Any

from app.core.config import get_settings
from app.services.source_fetcher import fetch_source

log = logging.getLogger(__name__)

_MAX_TEXT_CHARS = 8_000

_SYSTEM_PROMPT = """You are a factual accuracy checker for a legal court-event tracker.
You will be given:
  - A list of CLAIMED fields about a legal event (type, date, location, status, summary).
  - Extracted text from the primary source document.

Your job: for each claimed field, determine whether the source text supports it.

RULES — YOU MUST FOLLOW ALL OF THEM:
1. Output ONLY a JSON array.  No prose, no explanation outside the JSON.
2. Each element must be: {"field": string, "claim": string, "supported": true|false,
   "evidence_excerpt": string_or_null, "severity": "ok"|"warning"|"error"}.
3. Set severity="ok" when supported=true, severity="warning" when uncertain,
   severity="error" when the source contradicts the claim.
4. evidence_excerpt must be a short quote from the source text (≤80 chars) or null.
5. DO NOT produce guilt scores, danger scores, judge scores, or defendant scores.
6. DO NOT speculate about criminal culpability, mental state, or personal character.
7. If the source text is empty or clearly irrelevant, return an empty array [].
"""

_USER_TEMPLATE = """CLAIMED FIELDS:
{claims_json}

SOURCE TEXT (truncated to {char_limit} chars):
{source_text}

Return only the JSON array of field-level findings."""


# ---------------------------------------------------------------------------
# HTML stripping
# ---------------------------------------------------------------------------

class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._parts: list[str] = []
        self._skip_tags = {"script", "style", "noscript", "head", "nav",
                           "footer", "header"}
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag.lower() in self._skip_tags:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._skip_tags and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            stripped = data.strip()
            if stripped:
                self._parts.append(stripped)

    def get_text(self) -> str:
        return " ".join(self._parts)


def _strip_html(raw: str) -> str:
    parser = _TextExtractor()
    try:
        parser.feed(raw)
    except Exception:
        return raw
    return parser.get_text()


# ---------------------------------------------------------------------------
# Ollama call
# ---------------------------------------------------------------------------

def _call_ollama(
    prompt: str,
    model: str,
    base_url: str,
    timeout: int,
) -> str | None:
    """POST to Ollama /api/generate and return the response text, or None."""
    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0},
    }).encode()
    try:
        req = urllib.request.Request(
            f"{base_url.rstrip('/')}/api/generate",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status != 200:
                log.warning("source_verifier: Ollama HTTP %s", resp.status)
                return None
            body = json.loads(resp.read().decode("utf-8"))
            return body.get("response") or ""
    except Exception as exc:
        log.warning("source_verifier: Ollama call failed: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------

@dataclass
class SourceVerificationResult:
    record_type: str
    record_id: str | int
    source_url: str
    model_name: str
    findings: list[dict] = field(default_factory=list)
    status: str = "ok"
    error: str | None = None


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def verify_source(
    record_type: str,
    record_id: str | int,
    source_url: str,
    claimed_fields: dict[str, str],
) -> SourceVerificationResult:
    """Fetch source_url, extract text, ask Ollama to verify claimed_fields.

    claimed_fields example:
        {
            "event_type": "detention_order",
            "decision_date": "2024-01-15",
            "location": "Southern District of New York",
            "decision_result": "detained",
            "summary": "Order of detention under 18 U.S.C. § 3142.",
        }

    Returns a SourceVerificationResult with field-level findings.
    Never produces guilt scores, danger scores, judge scores, or defendant
    scores — only structural factual comparisons against the source text.
    """
    settings = get_settings()
    result = SourceVerificationResult(
        record_type=record_type,
        record_id=record_id,
        source_url=source_url,
        model_name=settings.ollama_model,
    )

    if not settings.ollama_enabled:
        result.status = "disabled"
        result.error = "Ollama verifier is disabled (JTA_OLLAMA_ENABLED=false)"
        return result

    # 1. Fetch source with snapshot persistence
    fetch_result = fetch_source(
        source_url,
        timeout=settings.ollama_timeout_seconds,
        store_snapshot=True,
    )
    if fetch_result.error or fetch_result.extracted_text is None:
        result.status = "fetch_failed"
        result.error = fetch_result.error or f"Could not fetch {source_url}"
        return result

    # 2. Truncate to max chars
    text = fetch_result.extracted_text[:_MAX_TEXT_CHARS]
    if not text.strip():
        result.status = "empty_source"
        result.error = "Source text was empty after extraction"
        return result

    # 3. Build prompt
    claims_json = json.dumps(claimed_fields, indent=2)
    user_msg = _USER_TEMPLATE.format(
        claims_json=claims_json,
        char_limit=_MAX_TEXT_CHARS,
        source_text=text,
    )
    full_prompt = f"{_SYSTEM_PROMPT}\n\n{user_msg}"

    # 4. Call Ollama
    response_text = _call_ollama(
        full_prompt,
        settings.ollama_model,
        settings.ollama_base_url,
        settings.ollama_timeout_seconds,
    )
    if response_text is None:
        result.status = "model_failed"
        result.error = "Ollama did not return a response"
        return result

    # 5. Parse JSON array from response
    findings = _parse_findings(response_text)
    if findings is None:
        result.status = "parse_failed"
        result.error = f"Could not parse model response as JSON findings"
        log.warning(
            "source_verifier: parse failure for %s/%s; raw=%r",
            record_type, record_id, response_text[:200],
        )
        return result

    # 6. Strip any forbidden scoring fields before storing
    result.findings = [_sanitize_finding(f) for f in findings]
    result.status = "ok"
    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FORBIDDEN_KEYS = {
    "guilt_score", "danger_score", "judge_score", "defendant_score",
    "risk_score", "threat_score", "culpability",
}

_ARRAY_RE = re.compile(r"\[.*?\]", re.DOTALL)


def _parse_findings(text: str) -> list[dict] | None:
    """Extract and validate a JSON array of findings from model output."""
    text = text.strip()
    # Try direct parse first
    if text.startswith("["):
        try:
            data = json.loads(text)
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
    # Try to extract embedded array
    match = _ARRAY_RE.search(text)
    if match:
        try:
            data = json.loads(match.group())
            if isinstance(data, list):
                return data
        except json.JSONDecodeError:
            pass
    return None


def _sanitize_finding(f: dict) -> dict:
    """Remove any forbidden scoring keys from a finding dict."""
    return {k: v for k, v in f.items() if k not in _FORBIDDEN_KEYS}
