"""Seed the source_registry table with known ingestion sources.

Idempotent: skips any row whose source_key already exists.
Fail-closed: all sources default to is_active=False.

Dev override: set JTA_CANADA_FIRST_DEV_ENABLE_SASKATOON=true *and*
APP_ENV=development to activate the saskatoon_crime pipeline locally.

Run standalone:
    python -m app.seed.source_registry
"""

from __future__ import annotations

import json
import pathlib

import yaml
from app.models.entities import SourceRegistry
from sqlalchemy import select
from sqlalchemy.inspection import inspect as sa_inspect
from sqlalchemy.orm import Session

# All sources are now defined in canada_saskatchewan_sources.yaml.
# Legacy hardcoded keys have been removed; YAML entries are authoritative.
_SOURCES: list[dict] = []

# ── YAML-driven Canada / Saskatchewan source definitions ─────────────────────
# Sources defined in the YAML override any matching source_key in _SOURCES.

_YAML_PATH = (
    pathlib.Path(__file__).parent.parent
    / "ingestion"
    / "sources"
    / "canada_saskatchewan_sources.yaml"
)

_LIST_FIELDS = ("allowed_domains", "creates")

# Sprint C fields whose YAML value can be a boolean False — coerce to string
# so SQLAlchemy's String column does not receive a Python bool.
_COERCE_TO_STR_FIELDS = ("terms_verified",)


def _load_yaml_sources() -> list[dict]:
    """Load sources from the YAML config, normalising list fields to JSON strings.

    Returns an empty list if the YAML file is missing (allows the module to
    import cleanly in environments where the file has not been deployed yet).
    """
    if not _YAML_PATH.exists():
        return []
    with _YAML_PATH.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    out: list[dict] = []
    for entry in raw.get("sources", []):
        normalised = dict(entry)
        for field in _LIST_FIELDS:
            val = normalised.get(field)
            if isinstance(val, list):
                normalised[field] = json.dumps(val)
        # Coerce bool-typed YAML values that map to String model columns.
        for field in _COERCE_TO_STR_FIELDS:
            val = normalised.get(field)
            if val is not None and not isinstance(val, str):
                normalised[field] = str(val).lower()
        out.append(normalised)
    return out


def _merged_sources() -> list[dict]:
    """Return the canonical source list, with YAML entries taking precedence."""
    yaml_sources = _load_yaml_sources()
    yaml_keys = {s["source_key"] for s in yaml_sources}
    base = [s for s in _SOURCES if s["source_key"] not in yaml_keys]
    return base + yaml_sources


def _source_registry_payload(spec: dict) -> dict:
    """Return only ORM-mapped SourceRegistry fields from a source spec."""
    valid_columns = {column.key for column in sa_inspect(SourceRegistry).columns}
    return {key: value for key, value in spec.items() if key in valid_columns}


# Required fields for machine_ingest sources that cannot be None/empty.
_MACHINE_INGEST_REQUIRED: tuple[str, ...] = (
    "parser",
    "parser_version",
    "allowed_domains",
    "source_class",
    "base_url",
    "public_record_authority",
    "requires_manual_review",
    "public_publish_default",
    "terms_url",
    "automation_status",
    # Sprint C: source provenance and access fields
    "confidence_class",
    "retention_policy",
    "canonical_url",
    "evidence_required",
    "terms_verified",
    "authentication_required",
    "rate_limit_policy",
)

# Fields whose type is boolean — checked with `is None` rather than truthiness
# to avoid flagging a legitimate `False` value as missing.
_BOOL_FIELDS: frozenset[str] = frozenset(
    {
        "requires_manual_review",
        "public_publish_default",
        "evidence_required",
        "authentication_required",
    }
)

_ALLOWED_MACHINE_INGEST_CONFIDENCE_CLASSES: frozenset[str] = frozenset(
    {
        "primary_official",
        "secondary_official",
        "tertiary",
        "official_court",
        "official_government",
    }
)

_ALLOWED_MACHINE_INGEST_RETENTION_POLICIES: frozenset[str] = frozenset(
    {"indefinite", "7_years", "rolling_90_days"}
)

_ALLOWED_MACHINE_INGEST_RATE_LIMIT_POLICIES: frozenset[str] = frozenset(
    {"none", "polite_1rps", "polite_5s_delay", "api_key_required"}
)

_ALLOWED_MACHINE_INGEST_AUTOMATION_STATUSES: frozenset[str] = frozenset(
    {"machine_ready_enabled", "machine_ready_disabled", "deprecated"}
)

_ALLOWED_MACHINE_INGEST_LIFECYCLE_STATES: frozenset[str] = frozenset(
    {"runnable", "runnable_disabled", "deprecated"}
)

_AUTOMATION_TO_LIFECYCLE_EXPECTED: dict[str, str] = {
    "machine_ready_enabled": "runnable",
    "machine_ready_disabled": "runnable_disabled",
    "deprecated": "deprecated",
}


def validate_machine_ingest_source_spec(spec: dict) -> list[str]:
    """Return violation slugs for a source spec that fails machine_ingest contracts.

    Call this during seeding or test assertions to reject incomplete specs
    before they reach the DB.  An empty return list means the spec is valid.

    Only applied when ``spec["source_class"] == "machine_ingest"``.  All other
    source classes are passed through without validation.
    """
    if spec.get("source_class") != "machine_ingest":
        return []

    violations: list[str] = []
    for field in _MACHINE_INGEST_REQUIRED:
        val = spec.get(field)
        # Boolean fields can legitimately be False — check only for None.
        # For all other fields treat an empty-list JSON string ("[]") as missing.
        if field in _BOOL_FIELDS:
            if val is None:
                violations.append(f"missing_{field}")
        elif not val or val == "[]":
            violations.append(f"missing_{field}")

    if violations:
        return violations

    confidence_class = str(spec.get("confidence_class") or "")
    if confidence_class not in _ALLOWED_MACHINE_INGEST_CONFIDENCE_CLASSES:
        violations.append("invalid_confidence_class")

    retention_policy = str(spec.get("retention_policy") or "")
    if retention_policy not in _ALLOWED_MACHINE_INGEST_RETENTION_POLICIES:
        violations.append("invalid_retention_policy")

    rate_limit_policy = str(spec.get("rate_limit_policy") or "")
    if rate_limit_policy not in _ALLOWED_MACHINE_INGEST_RATE_LIMIT_POLICIES:
        violations.append("invalid_rate_limit_policy")

    terms_verified = str(spec.get("terms_verified") or "").strip().lower()
    if terms_verified in {"", "false", "true", "none", "null"}:
        violations.append("invalid_terms_verified")

    canonical_url = str(spec.get("canonical_url") or "")
    if not (
        canonical_url.startswith("http://") or canonical_url.startswith("https://")
    ):
        violations.append("invalid_canonical_url")

    if spec.get("evidence_required") is not True:
        violations.append("evidence_required_must_be_true")

    automation_status = str(spec.get("automation_status") or "")
    lifecycle_state = str(spec.get("lifecycle_state") or "")
    if automation_status not in _ALLOWED_MACHINE_INGEST_AUTOMATION_STATUSES:
        violations.append("invalid_automation_status")
    if lifecycle_state not in _ALLOWED_MACHINE_INGEST_LIFECYCLE_STATES:
        violations.append("invalid_lifecycle_state")

    expected_lifecycle = _AUTOMATION_TO_LIFECYCLE_EXPECTED.get(automation_status)
    if expected_lifecycle and lifecycle_state != expected_lifecycle:
        violations.append("automation_lifecycle_mismatch")
    return violations


def validate_all_source_specs() -> dict[str, list[str]]:
    """Return source_key -> validation violations for every YAML/source spec."""
    return {
        spec["source_key"]: violations
        for spec in _merged_sources()
        if (violations := validate_machine_ingest_source_spec(spec))
    }


def seed_source_registry(db: Session) -> None:
    """Insert source registry rows that do not yet exist (idempotent)."""
    for spec in _merged_sources():
        violations = validate_machine_ingest_source_spec(spec)
        if violations:
            raise ValueError(
                f"Source {spec['source_key']!r} failed machine_ingest validation: {violations}"
            )
        existing = db.scalar(
            select(SourceRegistry).where(
                SourceRegistry.source_key == spec["source_key"]
            )
        )
        if existing is not None:
            continue
        db.add(SourceRegistry(**_source_registry_payload(spec)))
    db.commit()


# Fields whose DB value must match the spec.
# is_active is intentionally excluded — admins manage it via the frontend UI.
# auto_publish_enabled and requires_manual_review are intentionally excluded —
# these are operational flags controlled by operators and should never be
# silently reverted by a seed/repair run.
_REPAIR_FIELDS: tuple[str, ...] = (
    "source_name",
    "source_type",
    "source_tier",
    "fetch_method",
    "update_cadence",
    "country",
    "province_state",
    "city",
    "precision_level",
    # New metadata fields (YAML-sourced)
    "jurisdiction",
    "category",
    "priority",
    "public_record_authority",
    "base_url",
    "allowed_domains",
    "refresh_interval_minutes",
    "parser",
    "license",
    "license_url",
    "terms_url",
    "creates",
    "public_publish_default",
    "source_class",
    "parser_version",
    "automation_status",
    "lifecycle_state",
    "canonical_replacement_key",
    "status_reason",
    "operator_next_step",
    # Sprint C: source provenance and access contract fields
    "confidence_class",
    "retention_policy",
    "canonical_url",
    "evidence_required",
    "terms_verified",
    "authentication_required",
    "rate_limit_policy",
)


def repair_canada_first_defaults(db: Session, *, dry_run: bool = False) -> list[str]:
    """Repair existing registry rows that deviate from the current ``_SOURCES`` spec.

    Only the fields listed in :data:`_REPAIR_FIELDS` are checked — ``is_active``
    is intentionally excluded because admins manage it via the frontend UI.

    Args:
        db: SQLAlchemy session.
        dry_run: If *True*, collect diffs but do not write any changes.

    Returns:
        A list of human-readable change descriptions (one per field corrected).
    """
    changes: list[str] = []
    for spec in _merged_sources():
        violations = validate_machine_ingest_source_spec(spec)
        if violations:
            raise ValueError(
                f"Source {spec['source_key']!r} failed machine_ingest validation: {violations}"
            )
        row = db.scalar(
            select(SourceRegistry).where(
                SourceRegistry.source_key == spec["source_key"]
            )
        )
        if row is None:
            continue  # seed_source_registry handles inserts
        for field_name in _REPAIR_FIELDS:
            if field_name not in spec:
                continue
            current_val = getattr(row, field_name, None)
            spec_val = spec[field_name]
            if current_val != spec_val:
                changes.append(
                    f"{spec['source_key']}.{field_name}: {current_val!r} → {spec_val!r}"
                )
                if not dry_run:
                    setattr(row, field_name, spec_val)
    if not dry_run and changes:
        db.commit()
    return changes


if __name__ == "__main__":
    import argparse

    from app.db.session import SessionLocal

    parser = argparse.ArgumentParser(description="Source registry seed + repair")
    parser.add_argument(
        "--repair", action="store_true", help="Repair stale registry rows"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show changes without applying (implies --repair)",
    )
    args = parser.parse_args()

    with SessionLocal() as db:
        seed_source_registry(db)
        print("source_registry seeded")
        if args.repair or args.dry_run:
            changes = repair_canada_first_defaults(db, dry_run=args.dry_run)
            if not changes:
                print("No deviations found.")
            else:
                for msg in changes:
                    print(msg)
                if args.dry_run:
                    print("(dry run — no changes committed)")
                else:
                    print(f"{len(changes)} field(s) repaired.")
