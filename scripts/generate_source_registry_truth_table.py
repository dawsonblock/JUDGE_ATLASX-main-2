#!/usr/bin/env python3
"""Generate source registry truth table from YAML + adapter registry.

Creates markdown and JSON documents showing all sources, their lifecycle
readiness, and current runtime status.

Output:
- docs/SOURCE_REGISTRY_STATUS.md (human-readable markdown table)
- artifacts/proof/current/source_registry_status.json (machine-readable, lowercase)

Pass --proof-mode to require adapter registry import (exit 3 if unavailable)
and enforce that no deprecated source is runnable.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    from app.ingestion.source_adapters import ADAPTER_REGISTRY

    ADAPTER_REGISTRY_AVAILABLE = True
except Exception:
    ADAPTER_REGISTRY = {}
    ADAPTER_REGISTRY_AVAILABLE = False


def _source_display_name(source: dict) -> str:
    """Return the best available display name for a source registry entry.

    Fallback chain: source_name → name → source_key → source_id → UNKNOWN_SOURCE.
    Robust against stale dicts that omit one field.
    """
    return (
        source.get("source_name")
        or source.get("name")
        or source.get("source_key")
        or source.get("id")
        or source.get("source_id")
        or "UNKNOWN_SOURCE"
    )


def load_sources_yaml() -> list[dict[str, Any]]:
    """Load all sources from YAML."""
    yaml_path = (
        REPO_ROOT
        / "backend"
        / "app"
        / "ingestion"
        / "sources"
        / "canada_saskatchewan_sources.yaml"
    )
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    return list(data.get("sources", []))


def get_adapter_status(source: dict[str, Any]) -> tuple[bool | None, str, str]:
    """Resolve parser adapter state.

    Returns (adapter_exists, parser_key, adapter_state).
    adapter_exists is None when adapter registry import is unavailable.
    """
    parser_key = source.get("parser") or ""
    if not parser_key:
        return False, "", "missing_parser"
    if not ADAPTER_REGISTRY_AVAILABLE:
        return None, parser_key, "unknown"

    exists = parser_key in ADAPTER_REGISTRY
    return exists, parser_key, "found" if exists else "missing"


def compute_lifecycle_status(
    source: dict[str, Any],
    lifecycle_by_key: dict[str, str | None],
    *,
    adapter_exists: bool | None,
) -> dict[str, Any]:
    """Compute lifecycle-truthful status fields requested by proof."""
    blockers: list[str] = []

    source_key = source.get("source_key")
    source_class = source.get("source_class")
    lifecycle_state = source.get("lifecycle_state")
    automation_status = source.get("automation_status")
    canonical_replacement_key = source.get("canonical_replacement_key")
    canonical_now = lifecycle_state != "deprecated" and not canonical_replacement_key

    if source_class != "machine_ingest":
        blockers.append("non_machine_ingest_source")

    if lifecycle_state != "runnable":
        blockers.append(f"lifecycle_state={lifecycle_state}")

    if automation_status != "machine_ready_enabled":
        blockers.append(f"automation_status={automation_status}")

    if adapter_exists is None:
        blockers.append("adapter_registry_unavailable")
    elif adapter_exists is False:
        blockers.append("adapter_missing")

    # Deprecated sources must never appear canonical.
    if lifecycle_state == "deprecated":
        blockers.append("deprecated_source_noncanonical")
        canonical_now = False
        if not canonical_replacement_key:
            blockers.append("missing_canonical_replacement")
        elif canonical_replacement_key == source_key:
            blockers.append("replacement_self_reference")
        else:
            replacement_lifecycle = lifecycle_by_key.get(canonical_replacement_key)
            if replacement_lifecycle == "deprecated":
                blockers.append("replacement_deprecated")

    runnable_now = len(blockers) == 0

    # Enable readiness reflects transition preconditions, not active run state.
    enable_ready = (
        source_class == "machine_ingest"
        and lifecycle_state == "runnable_disabled"
        and bool(source.get("parser"))
        and bool(source.get("parser_version"))
        and bool(source.get("base_url"))
        and automation_status in {"machine_ready_disabled", "machine_ready_enabled"}
        and adapter_exists is not False
    )

    if lifecycle_state == "deprecated":
        enable_ready = False
        runnable_now = False

    return {
        "canonical_now": canonical_now,
        "runnable_now": runnable_now,
        "enable_ready": enable_ready,
        "blockers": blockers,
    }


def generate_truth_table_markdown(sources: list[dict[str, Any]]) -> str:
    """Generate markdown table of source registry status."""
    lifecycle_by_key = {
        source.get("source_key", ""): source.get("lifecycle_state")
        for source in sources
    }

    lines = [
        "# Source Registry Status",
        "",
        f"**Generated:** {datetime.now(timezone.utc).isoformat()}",
        "",
        f"**Total sources:** {len(sources)}",
        "",
        "| Source Key | Name | Jurisdiction | Class | Type | Lifecycle | Automation | Adapter State | Runnable Now | Enable Ready | Review Required | Status |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    for source in sources:
        source_key = source.get("source_key", "")
        name = _source_display_name(source).replace("|", "\\|")
        jurisdiction = source.get("jurisdiction", "")
        source_class = source.get("source_class", "")
        source_type = source.get("source_type", "")
        lifecycle_state = source.get("lifecycle_state", "")
        automation_status = source.get("automation_status", "")

        adapter_exists, _, adapter_state = get_adapter_status(source)
        lifecycle = compute_lifecycle_status(
            source,
            lifecycle_by_key,
            adapter_exists=adapter_exists,
        )

        runnable_mark = "✓" if lifecycle["runnable_now"] else "✗"
        enable_mark = "✓" if lifecycle["enable_ready"] else "✗"
        review_mark = "✓" if source.get("requires_manual_review", False) else "✗"
        alpha_status = source.get("alpha_status", "configured")

        lines.append(
            f"| `{source_key}` | {name} | {jurisdiction} | {source_class} | {source_type} | "
            f"{lifecycle_state} | {automation_status} | {adapter_state} | {runnable_mark} | "
            f"{enable_mark} | {review_mark} | {alpha_status} |"
        )

        extra: list[str] = []
        if source.get("canonical_replacement_key"):
            extra.append(f"replacement={source.get('canonical_replacement_key')}")
        if source.get("status_reason"):
            extra.append(f"reason={source.get('status_reason')}")
        if source.get("operator_next_step"):
            extra.append(f"next={source.get('operator_next_step')}")
        extra.append(f"canonical_now={lifecycle['canonical_now']}")
        if lifecycle["blockers"]:
            extra.append(f"blockers={','.join(lifecycle['blockers'])}")

        if extra:
            lines.append(f"| ↳ |  |  |  |  |  |  |  |  |  |  | {'; '.join(extra)} |")

    lines.extend(
        [
            "",
            "## Legend",
            "",
            "- **Lifecycle:** source lifecycle_state from YAML source-of-truth",
            "- **Automation:** source automation_status from YAML source-of-truth",
            "- **Adapter State:** `found`, `missing`, `unknown`, or `missing_parser`",
            "- **Runnable Now:** source can run immediately under lifecycle + adapter + automation checks",
            "- **Enable Ready:** source can safely transition via enable flow",
            "",
            "## Notes",
            "",
            "- Deprecated sources are never canonical and are not enable-ready.",
            "- If adapter registry import is unavailable, adapter state is `unknown` (not forced missing).",
        ]
    )

    return "\n".join(lines)


def generate_truth_table_json(sources: list[dict[str, Any]]) -> dict[str, Any]:
    """Generate JSON representation of source registry."""
    lifecycle_by_key = {
        source.get("source_key", ""): source.get("lifecycle_state")
        for source in sources
    }

    rows = []
    for source in sources:
        source_key = source.get("source_key", "")
        adapter_exists, adapter_key, adapter_state = get_adapter_status(source)
        lifecycle = compute_lifecycle_status(
            source,
            lifecycle_by_key,
            adapter_exists=adapter_exists,
        )

        row = {
            "source_key": source_key,
            "source_name": _source_display_name(source),
            "jurisdiction": source.get("jurisdiction", ""),
            "source_class": source.get("source_class", ""),
            "source_type": source.get("source_type", ""),
            "lifecycle_state": source.get("lifecycle_state"),
            "canonical_replacement_key": source.get("canonical_replacement_key"),
            "status_reason": source.get("status_reason"),
            "operator_next_step": source.get("operator_next_step"),
            "automation_status": source.get("automation_status", ""),
            "adapter_key": adapter_key,
            "adapter_exists": adapter_exists,
            "adapter_state": adapter_state,
            "parser": source.get("parser", ""),
            "requires_manual_review": source.get("requires_manual_review", False),
            "runnable_now": lifecycle["runnable_now"],
            "canonical_now": lifecycle["canonical_now"],
            "enable_ready": lifecycle["enable_ready"],
            "blockers": lifecycle["blockers"],
            "alpha_status": source.get("alpha_status", "configured"),
        }
        rows.append(row)

    runnable_count = sum(1 for r in rows if r["runnable_now"])
    enable_ready_count = sum(1 for r in rows if r["enable_ready"])
    deprecated_count = sum(
        1 for r in rows if r["lifecycle_state"] == "deprecated"
    )
    machine_ingest_count = sum(
        1 for r in rows if r["source_class"] == "machine_ingest"
    )
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "total_sources": len(sources),
        "summary": {
            "total_sources": len(sources),
            "machine_ingest_sources": machine_ingest_count,
            "runnable_now": runnable_count,
            "enable_ready": enable_ready_count,
            "deprecated": deprecated_count,
        },
        "sources": rows,
        "adapter_registry_size": len(ADAPTER_REGISTRY),
        "adapter_registry_available": ADAPTER_REGISTRY_AVAILABLE,
    }


def main() -> int:
    """Generate truth table and write to output files."""
    parser = argparse.ArgumentParser(description="Generate source registry truth artifacts")
    parser.add_argument(
        "--strict-adapter-registry",
        action="store_true",
        help="Fail if adapter registry import is unavailable",
    )
    parser.add_argument(
        "--proof-mode",
        action="store_true",
        help=(
            "Strict proof mode: requires adapter registry to be importable "
            "(exit 3 if not), and asserts no deprecated source is runnable."
        ),
    )
    args = parser.parse_args()

    strict = args.strict_adapter_registry or args.proof_mode
    if strict and not ADAPTER_REGISTRY_AVAILABLE:
        print("ERROR: adapter registry unavailable — backend env must be installed for proof mode")
        return 3

    try:
        sources = load_sources_yaml()
    except Exception as exc:
        print(f"ERROR: Failed to load YAML: {exc}")
        return 1

    if not sources:
        print("ERROR: No sources found in YAML")
        return 1

    try:
        markdown = generate_truth_table_markdown(sources)
        md_path = REPO_ROOT / "docs" / "SOURCE_REGISTRY_STATUS.md"
        md_path.parent.mkdir(parents=True, exist_ok=True)
        md_path.write_text(markdown, encoding="utf-8")
        print(f"✓ Generated {md_path}")
    except Exception as exc:
        print(f"ERROR: Failed to generate markdown: {exc}")
        return 1

    try:
        json_data = generate_truth_table_json(sources)
        json_path = REPO_ROOT / "artifacts" / "proof" / "current" / "source_registry_status.json"
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(json_data, indent=2), encoding="utf-8")
        print(f"✓ Generated {json_path}")
    except Exception as exc:
        print(f"ERROR: Failed to generate JSON: {exc}")
        return 1

    if args.proof_mode:
        deprecated_runnable = [
            row["source_key"]
            for row in json_data["sources"]
            if row["lifecycle_state"] == "deprecated" and row["runnable_now"]
        ]
        if deprecated_runnable:
            print(
                f"ERROR: proof-mode violation — deprecated sources marked runnable: "
                f"{deprecated_runnable}"
            )
            return 1

    print(f"\n✓ Truth table generation complete: {len(sources)} sources documented")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
