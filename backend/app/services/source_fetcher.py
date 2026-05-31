"""Source fetching service with snapshot persistence.

Provides URL fetching with:
- SSRF protection (private IPs, localhost blocked)
- Content hash storage
- SourceSnapshot persistence for provenance
- Size limits and timeout enforcement
- Content-type allowlist enforcement

NOTE: DNS Rebinding Limitation — This fetcher performs a DNS check before the
request, but the HTTP library may re-resolve DNS during the actual connection.
True DNS rebinding resistance requires routing fetches through a locked-down
egress proxy or sandboxed fetch worker. For production deployments, configure
JTA_FETCH_EGRESS_PROXY or use a dedicated sandboxed fetch worker.

Public API
----------
New callers should prefer ``app.security.safe_fetch.safe_fetch()`` which wraps
this module and adds domain allowlisting and a clean ``SafeFetchConfig``
interface.  The functions and constants below (``_PRIVATE_NETWORKS``,
``_is_safe_url``, ``FetchResult``, ``fetch_source``) remain importable for
backward compatibility and are re-used by ``safe_fetch`` to avoid duplication.
"""

from __future__ import annotations

import hashlib
import ipaddress
import logging
import os
import socket
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.entities import SourceSnapshot

log = logging.getLogger(__name__)

# Max download size (bytes)
_DEFAULT_MAX_BYTES = 512_000

# Allowed content types for fetched sources
ALLOWED_CONTENT_TYPES = {
    "text/html",
    "text/plain",
    "application/json",
    "application/pdf",
    "application/xml",
    "text/xml",
}


def _is_allowed_content_type(content_type: str) -> bool:
    """Return True if content_type starts with an allowed MIME type."""
    base = content_type.split(";")[0].strip().lower()
    return base in ALLOWED_CONTENT_TYPES


# Private/reserved IP ranges to block
_PRIVATE_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),  # Link-local
    ipaddress.ip_network("100.64.0.0/10"),  # CGNAT
    ipaddress.ip_network("224.0.0.0/4"),  # Multicast
    ipaddress.ip_network("240.0.0.0/4"),  # Reserved (class E)
    ipaddress.ip_network("fc00::/7"),  # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),  # IPv6 link-local
)


@dataclass
class FetchResult:
    """Result of a source fetch operation."""

    url: str
    final_url: str | None
    fetched_at: datetime
    http_status: int | None
    content_type: str | None
    headers: dict[str, str]
    raw_content: bytes | None
    raw_content_hash: str | None
    extracted_text: str | None
    extracted_text_hash: str | None
    error: str | None
    snapshot_id: int | None = None


def _host_in_allowlist(host: str, allowed_domains: frozenset[str]) -> bool:
    """Return True when host matches configured allowlist entries."""
    if not allowed_domains:
        return True
    bare = host.removeprefix("www.")
    return host in allowed_domains or bare in allowed_domains


def _is_safe_url(url: str, check_dns: bool = True) -> tuple[bool, str]:
    """Validate URL is safe to fetch (no SSRF).

    Args:
        url: URL to validate
        check_dns: If True, also check if hostname resolves to private IP
    """
    try:
        parsed = urllib.parse.urlparse(url)

        # Scheme check
        if parsed.scheme not in ("http", "https"):
            return False, f"scheme '{parsed.scheme}' not allowed"

        # Host check
        host = parsed.hostname
        if not host:
            return False, "missing hostname"

        # Localhost check
        if host.lower() in ("localhost", "127.0.0.1", "::1"):
            return False, "localhost not allowed"

        # Block cloud metadata IPs (direct and Azure/AWS variants)
        if host in (
            "169.254.169.254",
            "fd00:ec2::254",
            "metadata.google.internal",
            "metadata.internal",
            "100.100.100.200",
        ):
            return False, "cloud metadata IP blocked"

        # IP address check (blocks private ranges)
        is_ip = False
        try:
            addr = ipaddress.ip_address(host)
            is_ip = True
            for network in _PRIVATE_NETWORKS:
                if addr in network:
                    return False, f"private IP {host} not allowed"
        except ValueError:
            pass  # Not an IP, it's a hostname

        # DNS resolution check for hostnames (prevents DNS rebinding)
        if check_dns and not is_ip:
            try:
                resolved = socket.getaddrinfo(host, None)
                for family, _, _, _, sockaddr in resolved:
                    ip_str = sockaddr[0]
                    try:
                        addr = ipaddress.ip_address(ip_str)
                        for network in _PRIVATE_NETWORKS:
                            if addr in network:
                                return (
                                    False,
                                    f"hostname resolves to private IP {ip_str}",
                                )
                    except ValueError:
                        continue
            except socket.gaierror:
                return False, f"could not resolve hostname {host}"
            except Exception:
                pass  # Continue if DNS check fails

        return True, ""
    except Exception as exc:
        return False, f"URL parse error: {exc}"


class _SSRFRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Custom redirect handler that validates each redirect target."""

    max_redirections = 5

    def __init__(self, allowed_domains: frozenset[str] | None = None):
        super().__init__()
        self._allowed_domains = allowed_domains or frozenset()

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        """Override to validate redirect URL before following."""
        old_scheme = urllib.parse.urlparse(req.full_url).scheme.lower()
        new_scheme = urllib.parse.urlparse(newurl).scheme.lower()
        if old_scheme == "https" and new_scheme == "http":
            log.warning(
                "source_fetcher: blocked redirect downgrade from https to http: %s",
                newurl,
            )
            raise urllib.request.HTTPError(
                newurl,
                code,
                "Redirect blocked: https to http downgrade",
                headers,
                fp,
            )

        # Validate the new URL
        is_safe, reason = _is_safe_url(newurl, check_dns=True)
        if not is_safe:
            log.warning(
                "source_fetcher: blocked unsafe redirect to %s: %s", newurl, reason
            )
            raise urllib.request.HTTPError(
                newurl, code, f"Redirect blocked: {reason}", headers, fp
            )

        host = urllib.parse.urlparse(newurl).hostname or ""
        if self._allowed_domains and not _host_in_allowlist(
            host, self._allowed_domains
        ):
            log.warning(
                "source_fetcher: blocked redirect host %s not in allowlist", host
            )
            raise urllib.request.HTTPError(
                newurl,
                code,
                f"Redirect blocked: domain not in allowlist ({host})",
                headers,
                fp,
            )

        log.debug("source_fetcher: following redirect to %s", newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _build_fetch_opener(
    proxy_url: str | None,
    allowed_domains: frozenset[str] | None = None,
) -> urllib.request.OpenerDirector:
    """Build a redirect-safe opener with optional egress proxy routing."""
    redirect_handler = _SSRFRedirectHandler(allowed_domains=allowed_domains)
    if proxy_url:
        proxy_handler = urllib.request.ProxyHandler(
            {"http": proxy_url, "https": proxy_url}
        )
        return urllib.request.build_opener(proxy_handler, redirect_handler)
    return urllib.request.build_opener(redirect_handler)


def _sha256(data: bytes | str) -> str:
    """Compute SHA256 hash of data."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def _extract_text_from_html(raw_bytes: bytes, content_type: str) -> str:
    """Simple text extraction from HTML."""
    from html.parser import HTMLParser

    class TextExtractor(HTMLParser):
        def __init__(self):
            super().__init__()
            self.parts: list[str] = []
            self.skip = {"script", "style", "noscript"}
            self.skip_depth = 0

        def handle_starttag(self, tag, attrs):
            if tag in self.skip:
                self.skip_depth += 1

        def handle_endtag(self, tag):
            if tag in self.skip and self.skip_depth > 0:
                self.skip_depth -= 1

        def handle_data(self, data):
            if self.skip_depth == 0:
                self.parts.append(data)

    try:
        charset = "utf-8"
        if "charset=" in content_type:
            charset = content_type.split("charset=")[-1].split(";")[0].strip()
        text = raw_bytes.decode(charset, errors="replace")
        extractor = TextExtractor()
        extractor.feed(text)
        return " ".join(extractor.parts)
    except Exception as exc:
        log.warning("Text extraction failed: %s", exc)
        return ""


def fetch_source(
    url: str,
    timeout: int = 30,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    store_snapshot: bool = True,
    source_key: str | None = None,
    allowed_domains: frozenset[str] | None = None,
) -> FetchResult:
    """Fetch a source URL with SSRF protection and optional snapshot storage.

    Args:
        url: URL to fetch
        timeout: Request timeout in seconds
        max_bytes: Maximum bytes to download
        store_snapshot: Whether to persist to SourceSnapshot table

    Returns:
        FetchResult with content and provenance info
    """
    settings = get_settings()
    now = datetime.now(timezone.utc)

    result = FetchResult(
        url=url,
        final_url=None,
        fetched_at=now,
        http_status=None,
        content_type=None,
        headers={},
        raw_content=None,
        raw_content_hash=None,
        extracted_text=None,
        extracted_text_hash=None,
        error=None,
    )

    # SSRF check
    is_safe, reason = _is_safe_url(url)
    if not is_safe:
        result.error = f"SSRF blocked: {reason}"
        log.warning("source_fetcher: blocked unsafe URL %s: %s", url, reason)
        if store_snapshot:
            _persist_snapshot(result, settings, source_key=source_key)
        return result

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "JudgeTrackerAtlas/1.0 source-fetcher",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
            method="GET",
        )

        # Route through optional egress proxy when configured.
        proxy_url = os.environ.get("JTA_FETCH_EGRESS_PROXY")
        opener = _build_fetch_opener(
            proxy_url,
            allowed_domains=allowed_domains,
        )

        with opener.open(req, timeout=timeout) as resp:
            result.http_status = resp.status
            result.final_url = resp.geturl()
            result.content_type = resp.headers.get_content_type() or ""

            # Store sanitized headers
            for key, value in resp.headers.items():
                if key.lower() not in ("set-cookie", "authorization"):
                    result.headers[key] = value

            # Enforce content-type allowlist before reading body
            if result.content_type and not _is_allowed_content_type(
                result.content_type
            ):
                result.error = (
                    f"Rejected: unsupported content type: {result.content_type}"
                )
                result.raw_content = None  # Don't store unsafe content
                log.warning(
                    "source_fetcher: rejected unsupported content type %s for %s",
                    result.content_type,
                    url,
                )
            else:
                # Read with size limit. If the response exceeds max_bytes,
                # discard the body rather than persisting a truncated partial
                # snapshot.
                raw_content = resp.read(max_bytes + 1)
                if len(raw_content) > max_bytes:
                    result.error = f"Content exceeds max_bytes: {max_bytes}"
                    result.raw_content = None
                    result.raw_content_hash = None
                    result.extracted_text = None
                    result.extracted_text_hash = None
                    log.warning(
                        "source_fetcher: response exceeded max_bytes for %s; discarding body",
                        url,
                    )
                else:
                    result.raw_content = raw_content

                    # Compute hash
                    if result.raw_content:
                        result.raw_content_hash = _sha256(result.raw_content)

                    # Extract text for HTML content
                    if "text/html" in result.content_type and result.raw_content:
                        result.extracted_text = _extract_text_from_html(
                            result.raw_content, result.content_type
                        )
                        if result.extracted_text:
                            result.extracted_text_hash = _sha256(result.extracted_text)

        log.info(
            "source_fetcher: fetched %s (%s bytes)", url, len(result.raw_content or b"")
        )

    except urllib.error.HTTPError as exc:
        result.http_status = exc.code
        result.error = f"HTTP error {exc.code}: {exc.reason}"
        log.warning("source_fetcher: HTTP %s for %s", exc.code, url)
    except Exception as exc:
        result.error = f"Fetch failed: {exc}"
        log.warning("source_fetcher: fetch failed for %s: %s", url, exc)

    if store_snapshot:
        _persist_snapshot(result, settings, source_key=source_key)

    return result


def _persist_snapshot(
    result: FetchResult, settings, source_key: str | None = None
) -> int | None:
    """Persist fetch result to SourceSnapshot table using canonical writer."""
    try:
        from app.services.snapshot_writer import write_snapshot

        with SessionLocal() as db:
            snapshot = write_snapshot(
                db=db,
                source_url=result.url,
                fetched_at=result.fetched_at,
                content=result.raw_content or b"",
                extracted_text=result.extracted_text,
                headers=result.headers,
                http_status=result.http_status,
                content_type=result.content_type,
                error_message=result.error,
                source_key=source_key,
            )
            db.flush()  # Ensure ID is generated before commit
            db.commit()  # Persist to database
            result.snapshot_id = snapshot.id
            log.debug("source_fetcher: persisted snapshot id=%s", snapshot.id)
            return snapshot.id

    except Exception as exc:
        log.error("source_fetcher: failed to persist snapshot: %s", exc)
        return None


def get_snapshot_text(snapshot_id: int) -> str | None:
    """Retrieve extracted text from a snapshot by ID."""
    try:
        with SessionLocal() as db:
            snapshot = db.get(SourceSnapshot, snapshot_id)
            if snapshot:
                return snapshot.extracted_text
    except Exception as exc:
        log.warning("source_fetcher: failed to get snapshot %s: %s", snapshot_id, exc)
    return None
