#!/usr/bin/env python3
"""Verify source registry integrity against the canonical vocabulary.

Loads YAML source definitions and checks every source against the canonical
``ALL_AUTOMATION_STATUSES`` / ``ALL_LIFECYCLE_STATES`` sets exported by
``app.ingestion.automation_statuses``.  Also checks that every
``machine_ready_enabled`` source has a real (non-stub) adapter in the
``ADAPTER_REGISTRY`` and has ``parser_version`` set in the YAML.

Vocabulary violations (unknown status strings) caused by stale aliases such
as ``machine_ready`` are detected and reported as hard failures.

Exit codes:
  0 — all checks pass; ``source_registry_ok`` is ``true`` in JSON output
  1 — one or more registry violations detected
  2 — ADAPTER_REGISTRY or automation_statuses could not be imported

Usage::

    python scripts/verify_source_registry.py          # prose summary
    python scripts/verify_source_registry.py --json   # machine-readable JSON
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    import yaml  # noqa: E402
except ImportError:
    print("ERROR: PyYAML not installed — run: pip install pyyaml", file=sys.stderr)
    raise SystemExit(2)

try:
    from app.ingestion.source_adapters import ADAPTER_REGISTRY
except Exception as exc:  # noqa: BLE001
    print(f"ERROR: Cannot import ADAPTER_REGISTRY: {exc}", file=sys.stderr)
    raise SystemExit(2)

try:
    from app.ingestion.automation_statuses import (
        ALL_AUTOMATION_STATUSES,
        ALL_LIFECYCLE_STATES,
        MACHINE_READY_ENABLED,
        MACHINE_READY_DISABLED,
    )
except Exception as exc:  # noqa: BLE001
    print(f"ERROR: Cannot import automation_statuses: {exc}", file=sys.stderr)
    raise SystemExit(2)

# source_class values that should have machine-ingest adapters
_MACHINE_INGEST_CLASS = "machine_ingest"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_sources() -> list[dict[str, Any]]:
    yaml_path = (
        REPO_ROOT / "backend" / "app" / "ingestion" / "sources" / "canada_saskatchewan_sources.yaml"
    )
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    return list(data.get("sources", []))


def _is_stub_adapter(adapter_class: type) -> bool:
    """Return True if the class's fetch() method raises NotImplementedError.

    Done via AST inspection so it works even when the class cannot be
    instantiated without external services.
    """
    try:
        source_file = Path(sys.modules[adapter_class.__module__].__file__)
        src = source_file.read_text(encoding="utf-8")
    except Exception:
        return False

    tree = ast.parse(src)
    for class_node in ast.walk(tree):
        if not isinstance(class_node, ast.ClassDef):
            continue
        if class_node.name != adapter_class.__name__:
            continue
        for method in class_node.body:
            if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if method.name != "fetch":
                continue
            for stmt in ast.walk(method):
                if isinstance(stmt, ast.Raise) and stmt.exc is not None:
                    exc_node = stmt.exc
                    if isinstance(exc_node, ast.Call):
                        func = exc_node.func
                    elif isinstance(exc_node, ast.Name):
                        func = exc_node
                    else:
                        continue
                    name = (
                        func.id
                        if isinstance(func, ast.Name)
                        else (func.attr if isinstance(func, ast.Attribute) else "")
                    )
                    if name == "NotImplementedError":
                        return True
    return False


def _count_by_status(sources: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for s in sources:
        st = s.get("automation_status", "unknown")
        counts[st] = counts.get(st, 0) + 1
    return counts


# ---------------------------------------------------------------------------
# Main verification
# ---------------------------------------------------------------------------


def verify() -> dict[str, Any]:
    sources = _load_sources()
    status_counts = _count_by_status(sources)

    violations: list[dict[str, str]] = []
    registry_summary: list[dict[str, Any]] = []

    for source in sources:
        sk = source.get("source_key", "")
        parser_key = source.get("parser") or ""
        auto_status = source.get("automation_status") or ""
        lifecycle = source.get("lifecycle_state") or ""
        source_class = source.get("source_class") or ""
        parser_version_yaml = source.get("parser_version")

        source_violations: list[str] = []

        # 1. Vocabulary: automation_status must be a known value
        if auto_status not in ALL_AUTOMATION_STATUSES:
            source_violations.append(
                f"unknown_automation_status:{auto_status!r} "
                f"(not in ALL_AUTOMATION_STATUSES)"
            )

        # 2. Vocabulary: lifecycle_state must be a known value
        if lifecycle and lifecycle not in ALL_LIFECYCLE_STATES:
            source_violations.append(
                f"unknown_lifecycle_state:{lifecycle!r} "
                f"(not in ALL_LIFECYCLE_STATES)"
            )

        # 3. Consistency: machine_ready_enabled / machine_ready_disabled require machine_ingest
        if auto_status in {MACHINE_READY_ENABLED, MACHINE_READY_DISABLED}:
            if source_class != _MACHINE_INGEST_CLASS:
                source_violations.append(
                    f"machine_ready_on_non_ingest_class:{source_class!r} "
                    f"(automation_status={auto_status!r} requires source_class=machine_ingest)"
                )

        # 4. Adapter presence: machine_ready_enabled must have parser in ADAPTER_REGISTRY
        in_registry = parser_key in ADAPTER_REGISTRY if parser_key else False
        is_stub = False

        if auto_status == MACHINE_READY_ENABLED:
            if not parser_key:
                source_violations.append(
                    "machine_ready_enabled_missing_parser_key:parser field is null or empty"
                )
            elif not in_registry:
                source_violations.append(
                    f"adapter_missing_from_registry:{parser_key!r} "
                    f"not found in ADAPTER_REGISTRY"
                )
            else:
                is_stub = _is_stub_adapter(ADAPTER_REGISTRY[parser_key])
                if is_stub:
                    source_violations.append(
                        f"stub_adapter:{parser_key!r} fetch() raises NotImplementedError"
                    )
            # 5. Parser version: machine_ready_enabled must declare parser_version in YAML
            if not parser_version_yaml:
                source_violations.append(
                    "missing_parser_version:machine_ready_enabled source must set parser_version in YAML"
                )

        for v in source_violations:
            violations.append({"source_key": sk, "problem": v})

        registry_summary.append(
            {
                "source_key": sk,
                "automation_status": auto_status,
                "lifecycle_state": lifecycle,
                "source_class": source_class,
                "parser": parser_key or None,
                "parser_version": parser_version_yaml,
                "in_registry": in_registry,
                "is_stub": is_stub if in_registry else None,
                "violations": source_violations,
            }
        )

    source_registry_ok = len(violations) == 0

    result: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_registry_ok": source_registry_ok,
        "total_sources": len(sources),
        "status_counts": status_counts,
        "violations": violations,
        "stale_artifacts": [] if source_registry_ok else [
            "source_registry_status.json may be stale — re-run verify_source_registry.py --json"
        ],
        "registry_summary": registry_summary,
    }
    return result


def main() -> int:
    arg_parser = argparse.ArgumentParser(description=__doc__)
    arg_parser.add_argument(
        "--json", dest="json_output", action="store_true",
        help="Print machine-readable JSON result instead of prose.",
    )
    args = arg_parser.parse_args()

    result = verify()

    if args.json_output:
        json.dump(result, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        ok = result["source_registry_ok"]
        print("Source registry verification")
        print(f"  Generated at   : {result['generated_at']}")
        print(f"  Total sources  : {result['total_sources']}")
        print(f"  Status counts  : {result['status_counts']}")
        print(f"  Violations     : {len(result['violations'])}")
        for v in result["violations"]:
            print(f"    VIOLATION [{v['source_key']}]: {v['problem']}")
        if ok:
            print("PASS: source registry is consistent")
        else:
            print("FAIL: registry violations detected (see above)")

    return 0 if result["source_registry_ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
