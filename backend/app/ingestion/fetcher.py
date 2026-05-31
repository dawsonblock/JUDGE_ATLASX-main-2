"""Approved ingestion fetch interface.

All ingestion adapters MUST use ``fetch_for_ingestion()`` — never construct
``httpx.Client``, ``requests.Session``, ``aiohttp.ClientSession``, or
``urllib.request`` openers directly.  This ensures every outbound HTTP
request passes through the SSRF-protection gates in
``app.security.safe_fetch``.

Usage::

    from app.ingestion.fetcher import FetchCallable, fetch_for_ingestion

    class MyAdapter:
        def __init__(self, ..., fetcher: FetchCallable | None = None) -> None:
            self._fetcher = fetcher or fetch_for_ingestion
            self._allowed_domains = parse_allowed_domains(allowed_domains_json)

        def fetch(self) -> ...:
            result = self._fetcher(url, self._allowed_domains)
            if result.error:
                logger.error("Fetch blocked: %s", result.error)
                return []
            ...
"""
from __future__ import annotations

import json
import logging
import urllib.parse
from collections.abc import Callable, Iterable

from app.security.safe_fetch import SafeFetchConfig, safe_fetch
from app.services.source_fetcher import FetchResult

log = logging.getLogger(__name__)

_DEFAULT_MAX_BYTES = 512_000

# Type alias for an injectable fetcher callable used by adapters.
# Signature mirrors fetch_for_ingestion; use Callable[..., FetchResult] to
# allow test doubles without requiring the exact keyword-argument names.
FetchCallable = Callable[..., FetchResult]


def fetch_for_ingestion(
    url: str,
    allowed_domains: Iterable[str] = (),
    *,
    params: dict | None = None,
    timeout_seconds: int = 30,
    max_bytes: int = _DEFAULT_MAX_BYTES,
) -> FetchResult:
    """Fetch *url* with SSRF protection and optional domain allowlisting.

    The only approved way for ingestion adapters to make outbound HTTP
    requests.  Callers should always inspect ``result.error`` before
    consuming ``result.raw_content``.

    Args:
        url: Target URL (http/https only; private IPs rejected).
        allowed_domains: Restrict fetch to these hostnames.  An empty
            iterable skips the per-call domain allowlist (the built-in
            private-IP / localhost guard still applies).
        params: Optional query parameters appended to *url*.
        timeout_seconds: Per-request timeout (passed to safe_fetch).
        max_bytes: Maximum response body size in bytes.

    Returns:
        :class:`~app.services.source_fetcher.FetchResult` — check
        ``result.error`` before accessing ``result.raw_content``.
    """
    if params:
        sep = "&" if "?" in url else "?"
        url = url + sep + urllib.parse.urlencode(params)

    config = SafeFetchConfig(
        allowed_domains=frozenset(allowed_domains),
        timeout_seconds=timeout_seconds,
        max_response_bytes=max_bytes,
        store_snapshot=False,  # adapters manage their own evidence snapshots
    )
    return safe_fetch(url, config)


def parse_allowed_domains(allowed_domains_json: str | None) -> list[str]:
    """Parse a JSON-encoded domain list like ``'["api.canlii.org"]'``.

    Returns an empty list if the input is ``None``, empty, or malformed so
    adapters can always pass the result to :func:`fetch_for_ingestion`
    without a guard.
    """
    if not allowed_domains_json:
        return []
    try:
        parsed = json.loads(allowed_domains_json)
        if isinstance(parsed, list):
            return [str(d) for d in parsed]
        log.warning("allowed_domains_json is not a list: %r", allowed_domains_json)
        return []
    except (json.JSONDecodeError, TypeError):
        log.warning("Could not parse allowed_domains_json: %r", allowed_domains_json)
        return []
