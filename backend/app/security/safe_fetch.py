"""Formalized SSRF-safe fetch public API.

This module exposes a clean, documented interface over the SSRF-protection
logic implemented in ``app.services.source_fetcher``.  Prefer ``safe_fetch()``
over calling ``fetch_source()`` directly when you need:

* Programmatic per-call domain allowlisting
* Configurable timeout / size-cap overrides
* A standalone ``is_private_ip()`` predicate (e.g. for request-validation
  middleware outside the scheduler)

DNS Rebinding Limitation
------------------------
``_is_safe_url`` performs a DNS lookup *before* opening the TCP connection.
A malicious DNS server can serve a publicly-routable IP on the first lookup
and then rotate to a private address before the kernel opens the socket
(DNS TTL 0 / rebinding attack).

True resistance requires routing all outbound fetches through a locked-down
egress proxy.  Set ``JTA_FETCH_EGRESS_PROXY`` in the server environment — the
scheduler will forward all outbound requests through it.  See
``REPAIR_PROOF.md § DNS Rebinding`` for the documented limitation and
recommended mitigations.
"""

from __future__ import annotations

import ipaddress
import logging
import urllib.parse
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.services.source_fetcher import (
    FetchResult,
    _PRIVATE_NETWORKS,
    _is_safe_url,
    fetch_source,
)

log = logging.getLogger(__name__)

_DEFAULT_MAX_BYTES = 512_000


@dataclass(frozen=True)
class SafeFetchConfig:
    """Per-call configuration for :func:`safe_fetch`.

    All fields have safe defaults; construct with only the fields you need::

        cfg = SafeFetchConfig(
            allowed_domains=frozenset({"courts.gov", "canlii.org"}),
            timeout_seconds=15,
        )
        result = safe_fetch(url, cfg)
    """

    #: Restrict fetches to this set of hostnames.  Empty means no restriction.
    allowed_domains: frozenset[str] = field(default_factory=frozenset)
    #: Maximum number of redirects to follow (applied by the underlying opener).
    max_redirects: int = 5
    #: Request timeout in seconds.
    timeout_seconds: int = 30
    #: Hard cap on response body size in bytes.  Responses exceeding this are
    #: discarded (``result.raw_content`` is ``None``, ``result.error`` is set).
    max_response_bytes: int = _DEFAULT_MAX_BYTES
    #: Whether to persist a :class:`~app.models.entities.SourceSnapshot` row.
    store_snapshot: bool = True


def is_private_ip(ip_str: str) -> bool:
    """Return ``True`` if *ip_str* is a private, loopback, or reserved address.

    Covers:

    * RFC 1918 (10/8, 172.16/12, 192.168/16)
    * Loopback (127/8, ::1)
    * Link-local (169.254/16)
    * CGNAT (100.64/10)
    * IPv4 multicast (224/4) and reserved (240/4)
    * IPv6 unique-local (fc00::/7) and link-local (fe80::/10)

    Returns ``False`` for malformed *ip_str* rather than raising.
    """
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False

    if addr.is_loopback:
        return True

    for network in _PRIVATE_NETWORKS:
        try:
            if addr in network:
                return True
        except TypeError:
            # Mixed IPv4/IPv6 comparison; skip silently
            continue

    return False


def safe_fetch(url: str, config: SafeFetchConfig | None = None) -> FetchResult:
    """Fetch *url* with SSRF protection and optional domain allowlisting.

    The function applies two policy checks *before* opening a connection:

    1. **URL safety** — scheme must be ``http`` or ``https``; destination must
       not resolve to a private/loopback/reserved IP address.
    2. **Domain allowlist** — if ``config.allowed_domains`` is non-empty, the
       request hostname must appear in the set (``www.`` prefix is stripped for
       comparison).

    On any policy violation the call returns immediately with ``result.error``
    set and ``result.raw_content = None``.  No network connection is opened and
    no snapshot is persisted.

    Args:
        url:    Target URL (``http://`` or ``https://`` only).
        config: :class:`SafeFetchConfig`; uses defaults if ``None``.

    Returns:
        :class:`~app.services.source_fetcher.FetchResult`.  Always inspect
        ``result.error`` before consuming ``result.raw_content``.
    """
    if config is None:
        config = SafeFetchConfig()

    # ------------------------------------------------------------------
    # Gate 1: SSRF URL safety (scheme, private IP, DNS)
    # ------------------------------------------------------------------
    is_safe, reason = _is_safe_url(url)
    if not is_safe:
        log.warning("safe_fetch: blocked %s — %s", url, reason)
        return FetchResult(
            url=url,
            final_url=None,
            fetched_at=datetime.now(timezone.utc),
            http_status=None,
            content_type=None,
            headers={},
            raw_content=None,
            raw_content_hash=None,
            extracted_text=None,
            extracted_text_hash=None,
            error=f"SSRF blocked: {reason}",
        )

    # ------------------------------------------------------------------
    # Gate 2: Optional per-call domain allowlist
    # ------------------------------------------------------------------
    if config.allowed_domains:
        host = urllib.parse.urlparse(url).hostname or ""
        # Strip leading www. for comparison so callers don't need two entries.
        bare = host.removeprefix("www.")
        if host not in config.allowed_domains and bare not in config.allowed_domains:
            log.warning("safe_fetch: domain %s not in allowlist for %s", host, url)
            return FetchResult(
                url=url,
                final_url=None,
                fetched_at=datetime.now(timezone.utc),
                http_status=None,
                content_type=None,
                headers={},
                raw_content=None,
                raw_content_hash=None,
                extracted_text=None,
                extracted_text_hash=None,
                error=f"Domain not in allowlist: {host}",
            )

    # ------------------------------------------------------------------
    # Delegate to the underlying fetch implementation
    # ------------------------------------------------------------------
    return fetch_source(
        url=url,
        timeout=config.timeout_seconds,
        max_bytes=config.max_response_bytes,
        store_snapshot=config.store_snapshot,
        allowed_domains=config.allowed_domains,
    )
