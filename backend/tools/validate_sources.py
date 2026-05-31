"""Validate source registry definitions for contract and governance safety.

Usage:
  python -m backend.tools.validate_sources
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

# Ensure the backend directory is importable as top-level `app` when running
# `python -m backend.tools.*` from repository root.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.ingestion.automation_statuses import RUNNABLE_STATUSES
from app.seed.source_registry import _merged_sources, validate_machine_ingest_source_spec

_ALLOWED_SOURCE_CLASSES = {
    "machine_ingest",
    "portal_reference",
    "manual_reference",
    "manual_upload",
    "disabled_stub",
    "manual_review",
    "experimental",
    "reference_only",
    "architecture_reference",
    None,
}


def _check_duplicate_source_keys(sources: list[dict]) -> list[str]:
    counts = Counter(s["source_key"] for s in sources)
    return [f"duplicate_source_key:{k}" for k, v in counts.items() if v > 1]


def _check_schema_and_policy(sources: list[dict]) -> list[str]:
    errors: list[str] = []
    for src in sources:
        key = src.get("source_key", "<missing>")
        source_class = src.get("source_class")
        if source_class not in _ALLOWED_SOURCE_CLASSES:
            errors.append(f"{key}:unknown_source_class:{source_class}")

        # Publication controls must be explicit.
        if "requires_manual_review" not in src:
            errors.append(f"{key}:missing_requires_manual_review")
        if "public_publish_default" not in src:
            errors.append(f"{key}:missing_public_publish_default")

        # Disabled/portal/manual classes must not be runnable by status.
        if source_class in {"disabled_stub", "portal_reference", "manual_upload", "manual_review"}:
            if src.get("automation_status") in RUNNABLE_STATUSES:
                errors.append(f"{key}:non_runnable_class_has_runnable_status")

        # Machine-ingest contract completeness.
        errors.extend(f"{key}:{v}" for v in validate_machine_ingest_source_spec(src))

        # JSON-string list fields sanity.
        for field_name in ("allowed_domains", "creates"):
            value = src.get(field_name)
            if value is None:
                continue
            if isinstance(value, str):
                try:
                    parsed = json.loads(value)
                except json.JSONDecodeError:
                    errors.append(f"{key}:invalid_json:{field_name}")
                    continue
                if not isinstance(parsed, list):
                    errors.append(f"{key}:invalid_json_list:{field_name}")
            elif not isinstance(value, list):
                errors.append(f"{key}:unsupported_type:{field_name}")

        # Phase 7: Tighten validation - require adapter configuration for machine_ingest sources
        if source_class == "machine_ingest":
            if "adapter" not in src:
                errors.append(f"{key}:missing_adapter_configuration")
            elif not src["adapter"]:
                errors.append(f"{key}:empty_adapter_configuration")

        # Phase 7: Require test fixtures for all sources
        if "test_fixtures" not in src:
            errors.append(f"{key}:missing_test_fixtures")
        elif not src["test_fixtures"]:
            errors.append(f"{key}:empty_test_fixtures")

        # Phase 7: Require deprecation policy for deprecated sources
        lifecycle_state = src.get("lifecycle_state")
        if lifecycle_state == "deprecated":
            if "deprecation_policy" not in src:
                errors.append(f"{key}:missing_deprecation_policy")
            elif not src["deprecation_policy"]:
                errors.append(f"{key}:empty_deprecation_policy")

        # Phase 7: Require public status flag for public sources
        if src.get("public_publish_default") is True:
            if "public_status" not in src:
                errors.append(f"{key}:missing_public_status_flag")
            elif src["public_status"] is None:
                errors.append(f"{key}:null_public_status_flag")

        # Phase 7: Require secret requirements for sources that need secrets
        if src.get("requires_secrets", False):
            if "secret_requirements" not in src:
                errors.append(f"{key}:missing_secret_requirements")
            elif not src["secret_requirements"]:
                errors.append(f"{key}:empty_secret_requirements")

    return errors


def main() -> int:
    sources = _merged_sources()
    errors: list[str] = []
    errors.extend(_check_duplicate_source_keys(sources))
    errors.extend(_check_schema_and_policy(sources))

    if errors:
        print("SOURCE VALIDATION: FAIL")
        for err in errors:
            print(f"- {err}")
        return 1

    print("SOURCE VALIDATION: PASS")
    print(f"sources_checked={len(sources)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
