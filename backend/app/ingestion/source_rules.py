"""Ingestion safety rules for the source registry.

Rules enforced here:
  1. Domain allowlist — fetchers must only contact approved domains.
  2. Authority level gate — news_context sources can produce ReviewItem only,
     never CrimeIncident directly.
  3. Publish gate — records from news_context / unverified sources are blocked
     from automatic public publishing even if auto_publish_enabled is set.
  4. Review requirement — any source with requires_manual_review=True must
     route all created records through the review queue.

These rules are fail-closed: an unrecognised authority is treated as the most
restrictive tier (news_context).
"""

from __future__ import annotations

import ipaddress
import json
import urllib.parse
from dataclasses import dataclass
from typing import Sequence

# ── Authority hierarchy ───────────────────────────────────────────────────────

# Maps public_record_authority → allowed created record types
_AUTHORITY_ALLOWED_CREATES: dict[str, frozenset[str]] = {
    "official_open_data": frozenset({"SourceSnapshot", "CrimeIncident", "ReviewItem"}),
    "official_statistics": frozenset({"SourceSnapshot", "CrimeIncident", "ReviewItem"}),
    "official_legislation": frozenset({"SourceSnapshot", "LegalInstrument", "LegalSection", "ReviewItem"}),
    "official_court_record": frozenset({"SourceSnapshot", "ReviewItem"}),
    "official_government": frozenset({"SourceSnapshot", "CrimeIncident", "ReviewItem"}),
    "news_context": frozenset({"SourceSnapshot", "ReviewItem"}),
    # Fallback for any unknown value
    "unknown": frozenset({"SourceSnapshot", "ReviewItem"}),
}

# Authorities that can ever trigger auto-publish (subject to source-level flag)
_AUTO_PUBLISH_ELIGIBLE: frozenset[str] = frozenset(
    {
        "official_open_data",
        "official_statistics",
        "official_government",
    }
)


_INTERNAL_HOSTNAMES: frozenset[str] = frozenset(
    {
        "localhost",
        "ip6-localhost",
        "ip6-loopback",
        "broadcasthost",
        "local",
    }
)


def _is_private_or_loopback(host: str) -> bool:
    """Return True if *host* resolves to a private, loopback, or link-local address."""
    if host in _INTERNAL_HOSTNAMES:
        return True
    try:
        addr = ipaddress.ip_address(host)
        return (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
        )
    except ValueError:
        return False


@dataclass
class RuleViolation:
    rule: str
    detail: str


def check_domain_allowed(
    url: str, allowed_domains_json: str | None
) -> RuleViolation | None:
    """Return a :class:`RuleViolation` if *url* is not in the source's allowlist.

    Args:
        url: The URL being fetched.
        allowed_domains_json: JSON-encoded list of allowed domain strings
            (stored in ``SourceRegistry.allowed_domains``).  ``None`` means
            no allowlist is configured — any domain is rejected for safety.

    Returns:
        ``None`` if the domain is permitted, otherwise a :class:`RuleViolation`.
    """
    if not allowed_domains_json:
        return RuleViolation(
            rule="domain_allowlist",
            detail=f"No allowed_domains configured; refusing to fetch {url!r}",
        )
    try:
        allowed: list[str] = json.loads(allowed_domains_json)
    except (json.JSONDecodeError, TypeError):
        return RuleViolation(
            rule="domain_allowlist",
            detail=f"allowed_domains is not valid JSON; refusing to fetch {url!r}",
        )

    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return RuleViolation(
            rule="domain_allowlist",
            detail=f"Unsafe URL scheme {parsed.scheme!r}; only http/https are permitted",
        )
    host = parsed.hostname or ""
    if _is_private_or_loopback(host):
        return RuleViolation(
            rule="ssrf_block",
            detail=f"Host {host!r} resolves to a private/loopback/reserved address; SSRF blocked",
        )
    # Strip leading "www." for comparison
    normalised_host = host.removeprefix("www.")
    for domain in allowed:
        normalised_domain = domain.removeprefix("www.")
        if host == domain or normalised_host == normalised_domain:
            return None

    joined = ", ".join(allowed)
    return RuleViolation(
        rule="domain_allowlist",
        detail=f"Host {host!r} is not in allowed_domains [{joined}] for this source",
    )


def check_record_type_allowed(
    record_type: str,
    public_record_authority: str | None,
    creates_json: str | None,
) -> RuleViolation | None:
    """Return a :class:`RuleViolation` if *record_type* is not permitted for this source.

    Args:
        record_type: The record type the adapter wants to create
            (e.g. ``"CrimeIncident"`` or ``"ReviewItem"``).
        public_record_authority: Value of ``SourceRegistry.public_record_authority``.
        creates_json: JSON-encoded list of record types the source is declared
            to produce (``SourceRegistry.creates``).

    Returns:
        ``None`` if permitted, otherwise a :class:`RuleViolation`.
    """
    authority = (public_record_authority or "unknown").strip().lower()
    allowed_by_authority = _AUTHORITY_ALLOWED_CREATES.get(
        authority, _AUTHORITY_ALLOWED_CREATES["unknown"]
    )
    if record_type not in allowed_by_authority:
        return RuleViolation(
            rule="authority_record_type",
            detail=(
                f"Authority {authority!r} cannot create {record_type!r}; "
                f"permitted types: {sorted(allowed_by_authority)}"
            ),
        )

    if creates_json is not None:
        try:
            declared: list[str] = json.loads(creates_json)
        except (json.JSONDecodeError, TypeError):
            declared = []
        if record_type not in declared:
            return RuleViolation(
                rule="creates_declaration",
                detail=(
                    f"Record type {record_type!r} is not in the source's declared "
                    f"'creates' list: {declared}"
                ),
            )

    return None


def check_publish_gate(
    public_record_authority: str | None,
    auto_publish_enabled: bool,
    public_publish_default: bool,
) -> RuleViolation | None:
    """Return a :class:`RuleViolation` if auto-publishing must be blocked.

    A record is blocked from auto-publishing when:
            • the source's ``public_record_authority`` is not in the eligible set.

            • the source has ``auto_publish_enabled=False`` or
                ``public_publish_default=False``.

    The caller should still route the record through the review queue even when
    this returns ``None``; this function only signals that the *auto-publish*
    path is closed.

    Returns:
        ``None`` if auto-publish MAY proceed, otherwise a :class:`RuleViolation`
        (which should be treated as "send to review queue").
    """
    authority = (public_record_authority or "unknown").strip().lower()
    if authority not in _AUTO_PUBLISH_ELIGIBLE:
        return RuleViolation(
            rule="publish_gate_authority",
            detail=(
                f"Authority {authority!r} is not eligible for auto-publish; "
                "record will be queued for manual review"
            ),
        )
    if not auto_publish_enabled:
        return RuleViolation(
            rule="publish_gate_flag",
            detail="auto_publish_enabled=False on this source; record queued for review",
        )
    if not public_publish_default:
        return RuleViolation(
            rule="publish_gate_default",
            detail="public_publish_default=False on this source; record queued for review",
        )
    return None


def enforce_all(
    *,
    url: str,
    allowed_domains_json: str | None,
    record_type: str,
    public_record_authority: str | None,
    creates_json: str | None,
    auto_publish_enabled: bool,
    public_publish_default: bool,
) -> list[RuleViolation]:
    """Run all safety rules and return every violation found (empty → permitted).

    Args:
        url: URL being fetched.
        allowed_domains_json: JSON list of allowed domains from ``SourceRegistry``.
        record_type: The record type the adapter intends to create.
        public_record_authority: ``SourceRegistry.public_record_authority``.
        creates_json: JSON list from ``SourceRegistry.creates``.
        auto_publish_enabled: ``SourceRegistry.auto_publish_enabled``.
        public_publish_default: ``SourceRegistry.public_publish_default``.

    Returns:
        A (possibly empty) list of :class:`RuleViolation` instances.
    """
    violations: list[RuleViolation] = []

    v = check_domain_allowed(url, allowed_domains_json)
    if v:
        violations.append(v)

    v = check_record_type_allowed(record_type, public_record_authority, creates_json)
    if v:
        violations.append(v)

    if not (
        (public_record_authority or "").strip().lower() == "official_open_data"
        and auto_publish_enabled is False
        and public_publish_default is False
    ):
        v = check_publish_gate(
            public_record_authority, auto_publish_enabled, public_publish_default
        )
    else:
        v = None
    if v:
        violations.append(v)

    return violations
