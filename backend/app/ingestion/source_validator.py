"""Validate a SourceRegistry row against the ingestion contracts before running."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class SourceValidationResult:
    ok: bool
    source_key: str
    violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def validate_source(source) -> SourceValidationResult:
    """Validate a SourceRegistry ORM instance against ingestion requirements.

    Returns SourceValidationResult with ok=True only if all requirements pass.
    """
    violations: list[str] = []
    warnings: list[str] = []
    key = getattr(source, "source_key", "<unknown>")

    if not getattr(source, "source_key", None):
        violations.append("source_key is required")

    if not getattr(source, "base_url", None):
        violations.append("base_url is required")

    source_class = getattr(source, "source_class", None)
    if source_class in (None, "machine_ingest"):
        if not getattr(source, "parser_version", None):
            violations.append("parser_version is required for machine_ingest sources")

    if not getattr(source, "jurisdiction", None):
        warnings.append("jurisdiction not set — evidence provenance incomplete")

    if not getattr(source, "data_format", None):
        warnings.append("data_format not set")

    return SourceValidationResult(
        ok=len(violations) == 0,
        source_key=key,
        violations=violations,
        warnings=warnings,
    )
