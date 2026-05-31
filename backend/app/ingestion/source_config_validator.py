"""Strict validation for source registry configuration mutations.

Validates allowed_domains, base_url, parser, and config_json before
they are stored in the database.  All validation is fail-closed:
unknown or suspicious values are rejected with a clear error message.

Used by the admin PATCH route to prevent storing dangerous source configs.
"""
from __future__ import annotations

import ipaddress
import json
import re
import urllib.parse
from dataclasses import dataclass, field
from typing import Any

from app.models.entities import SourceRegistry

# Schemes that are never allowed in base_url
_BLOCKED_SCHEMES = frozenset(
    {"file", "ftp", "ftps", "gopher", "data", "javascript", "vbscript", "ldap", "ldaps"}
)

# Hostnames that are never allowed in allowed_domains or base_url
_BLOCKED_HOSTNAMES = frozenset(
    {
        "localhost",
        "ip6-localhost",
        "ip6-loopback",
        "broadcasthost",
        "local",
        "0.0.0.0",
        "::1",
        "[::]",
    }
)

# Regex for a valid hostname (no scheme, no path, no port)
_HOSTNAME_RE = re.compile(
    r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}$"
)


@dataclass
class ConfigValidationError:
    """A single validation error for a source config field."""

    field: str
    message: str


@dataclass
class ConfigValidationResult:
    """Result of validating a source configuration update."""

    errors: list[ConfigValidationError] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return len(self.errors) == 0

    def add(self, field: str, message: str) -> None:
        self.errors.append(ConfigValidationError(field=field, message=message))

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": [{"field": e.field, "message": e.message} for e in self.errors],
        }


def _is_private_ip(host: str) -> bool:
    """Return True if host is a private, loopback, or reserved IP address."""
    try:
        addr = ipaddress.ip_address(host)
        return (
            addr.is_private
            or addr.is_loopback
            or addr.is_link_local
            or addr.is_reserved
            or addr.is_multicast
        )
    except ValueError:
        return False


def _is_blocked_hostname(host: str) -> bool:
    """Return True if the hostname is blocked (localhost, private IP, etc.)."""
    host_lower = host.lower().strip(".")
    if host_lower in _BLOCKED_HOSTNAMES:
        return True
    if _is_private_ip(host_lower):
        return True
    # Block hostnames ending in .local, .internal, .intranet, .lan, .corp
    blocked_tlds = {".local", ".internal", ".intranet", ".lan", ".corp", ".home"}
    if any(host_lower.endswith(tld) for tld in blocked_tlds):
        return True
    return False


def validate_allowed_domains(value: str | None) -> list[ConfigValidationError]:
    """Validate the allowed_domains field.

    Rules:
    - Must be a JSON array of strings
    - Every item must be a valid hostname (no scheme, no path, no port)
    - No localhost or private IPs
    - No wildcards unless explicitly a subdomain wildcard (*.example.com)
    """
    errors: list[ConfigValidationError] = []
    if value is None:
        return errors

    try:
        domains = json.loads(value)
    except json.JSONDecodeError:
        errors.append(ConfigValidationError(
            field="allowed_domains",
            message="Must be a valid JSON array of hostname strings.",
        ))
        return errors

    if not isinstance(domains, list):
        errors.append(ConfigValidationError(
            field="allowed_domains",
            message="Must be a JSON array, not an object or scalar.",
        ))
        return errors

    for i, domain in enumerate(domains):
        if not isinstance(domain, str):
            errors.append(ConfigValidationError(
                field="allowed_domains",
                message=f"Item {i}: must be a string hostname, got {type(domain).__name__}.",
            ))
            continue

        domain = domain.strip()

        # Reject if it looks like a URL (has scheme or path)
        if "://" in domain or "/" in domain:
            errors.append(ConfigValidationError(
                field="allowed_domains",
                message=f"Item {i}: '{domain}' must be a hostname only (no scheme or path).",
            ))
            continue

        # Strip leading wildcard for validation
        check_host = domain.lstrip("*.")

        if _is_blocked_hostname(check_host):
            errors.append(ConfigValidationError(
                field="allowed_domains",
                message=f"Item {i}: '{domain}' is a blocked hostname (localhost/private IP).",
            ))
            continue

        # Validate hostname format
        if not _HOSTNAME_RE.match(check_host):
            errors.append(ConfigValidationError(
                field="allowed_domains",
                message=f"Item {i}: '{domain}' is not a valid hostname.",
            ))

    return errors


def validate_base_url(
    value: str | None,
    allowed_domains: str | None = None,
) -> list[ConfigValidationError]:
    """Validate the base_url field.

    Rules:
    - Must be http or https
    - Must not be localhost or private IP
    - Must not use blocked schemes
    - If allowed_domains is also being set, hostname must be in allowed_domains
    """
    errors: list[ConfigValidationError] = []
    if value is None:
        return errors

    try:
        parsed = urllib.parse.urlparse(value)
    except Exception:
        errors.append(ConfigValidationError(
            field="base_url",
            message="Must be a valid URL.",
        ))
        return errors

    scheme = parsed.scheme.lower()
    if scheme in _BLOCKED_SCHEMES:
        errors.append(ConfigValidationError(
            field="base_url",
            message=f"Scheme '{scheme}' is not allowed. Use http or https.",
        ))
        return errors

    if scheme not in ("http", "https"):
        errors.append(ConfigValidationError(
            field="base_url",
            message=f"Scheme '{scheme}' is not allowed. Use http or https.",
        ))
        return errors

    host = parsed.hostname or ""
    if not host:
        errors.append(ConfigValidationError(
            field="base_url",
            message="URL must have a valid hostname.",
        ))
        return errors

    if _is_blocked_hostname(host):
        errors.append(ConfigValidationError(
            field="base_url",
            message=f"Hostname '{host}' is blocked (localhost/private IP).",
        ))
        return errors

    # If allowed_domains is provided, hostname must be in the list
    if allowed_domains:
        try:
            domains = json.loads(allowed_domains)
            if isinstance(domains, list):
                # Normalize: strip www. prefix and wildcards for comparison
                normalized_domains = {d.lstrip("*.").lstrip("www.") for d in domains}
                normalized_host = host.lstrip("www.")
                if normalized_host not in normalized_domains:
                    errors.append(ConfigValidationError(
                        field="base_url",
                        message=(
                            f"Hostname '{host}' is not in the allowed_domains list. "
                            "Add it to allowed_domains before setting base_url."
                        ),
                    ))
        except (json.JSONDecodeError, TypeError):
            pass  # allowed_domains validation handles this separately

    return errors


def validate_parser(value: str | None) -> list[ConfigValidationError]:
    """Validate the parser field.

    Rules:
    - Must exist in ADAPTER_REGISTRY
    """
    errors: list[ConfigValidationError] = []
    if value is None:
        return errors

    from app.ingestion.source_adapters import ADAPTER_REGISTRY

    if value not in ADAPTER_REGISTRY:
        known = sorted(ADAPTER_REGISTRY.keys())
        errors.append(ConfigValidationError(
            field="parser",
            message=(
                f"Parser '{value}' is not registered. "
                f"Known parsers: {', '.join(known)}."
            ),
        ))
    return errors


def validate_config_json(
    value: str | None,
    parser: str | None = None,
) -> list[ConfigValidationError]:
    """Validate the config_json field.

    Rules:
    - Must be valid JSON
    - Must be a JSON object (dict), not array or scalar
    - Parser-specific key validation where possible
    """
    errors: list[ConfigValidationError] = []
    if value is None:
        return errors

    try:
        config = json.loads(value)
    except json.JSONDecodeError as exc:
        errors.append(ConfigValidationError(
            field="config_json",
            message=f"Must be valid JSON: {exc}",
        ))
        return errors

    if not isinstance(config, dict):
        errors.append(ConfigValidationError(
            field="config_json",
            message="Must be a JSON object (dict), not an array or scalar.",
        ))
        return errors

    # Parser-specific validation
    if parser == "canlii_api":
        databases = config.get("databases")
        if databases is not None:
            if not isinstance(databases, list) or not all(isinstance(d, str) for d in databases):
                errors.append(ConfigValidationError(
                    field="config_json",
                    message="canlii_api: 'databases' must be a list of strings.",
                ))
        result_count = config.get("result_count")
        if result_count is not None:
            if not isinstance(result_count, int) or result_count < 1 or result_count > 100:
                errors.append(ConfigValidationError(
                    field="config_json",
                    message="canlii_api: 'result_count' must be an integer between 1 and 100.",
                ))

    if parser == "federal_court_html":
        year = config.get("year")
        if year is not None:
            if not isinstance(year, int) or year < 1972 or year > 2100:
                errors.append(ConfigValidationError(
                    field="config_json",
                    message="federal_court_html: 'year' must be an integer between 1972 and 2100.",
                ))

    if parser == "ckan_api":
        resource_id = config.get("resource_id")
        if resource_id is not None and not isinstance(resource_id, str):
            errors.append(ConfigValidationError(
                field="config_json",
                message="ckan_api: 'resource_id' must be a string.",
            ))

    return errors


def validate_source_update(
    *,
    allowed_domains: str | None = None,
    base_url: str | None = None,
    parser: str | None = None,
    config_json: str | None = None,
) -> ConfigValidationResult:
    """Validate all source configuration fields in a single call.

    Returns a :class:`ConfigValidationResult` with all errors found.
    """
    result = ConfigValidationResult()

    # Validate each field
    for err in validate_allowed_domains(allowed_domains):
        result.errors.append(err)

    for err in validate_base_url(base_url, allowed_domains):
        result.errors.append(err)

    for err in validate_parser(parser):
        result.errors.append(err)

    for err in validate_config_json(config_json, parser):
        result.errors.append(err)

    return result


def can_run_source(source: SourceRegistry) -> tuple[bool, list[str]]:
    """Return whether a SourceRegistry row may execute an adapter run.

    This is the fail-closed runtime gate used by admin ingestion paths.  It is
    stricter than enablement: reference/manual/stub sources are never runnable.
    """
    if not isinstance(source, SourceRegistry):
        return False, ["invalid_source_type"]

    reasons: list[str] = []
    if source.is_active is not True:
        reasons.append("source_inactive")
    if source.source_class != "machine_ingest":
        reasons.append(f"source_class_not_runnable:{source.source_class!r}")
    lifecycle_state = source.lifecycle_state
    if lifecycle_state != "runnable":
        reasons.append(
            f"lifecycle_state_not_runnable:{source.lifecycle_state!r}"
        )
    if source.automation_status != "machine_ready_enabled":
        reasons.append(
            f"automation_status_not_enabled:{source.automation_status!r}"
        )
    if not source.parser:
        reasons.append("missing_parser")
    else:
        from app.ingestion.source_adapters import ADAPTER_REGISTRY

        if source.parser not in ADAPTER_REGISTRY:
            reasons.append(f"parser_not_registered:{source.parser}")
    if not source.parser_version:
        reasons.append("missing_parser_version")

    if not source.allowed_domains or source.allowed_domains in ("[]", ""):
        reasons.append("missing_allowed_domains")
    else:
        reasons.extend(
            f"{e.field}:{e.message}"
            for e in validate_allowed_domains(source.allowed_domains)
        )
    if not source.base_url:
        reasons.append("missing_base_url")
    else:
        reasons.extend(
            f"{e.field}:{e.message}"
            for e in validate_base_url(source.base_url, source.allowed_domains)
        )
    if source.requires_manual_review is not True:
        reasons.append("manual_review_required")
    if (
        source.public_publish_default is True
        and source.source_tier != "official_government_statistics"
    ):
        reasons.append("public_publish_default_for_individual_records")
    return len(reasons) == 0, reasons
