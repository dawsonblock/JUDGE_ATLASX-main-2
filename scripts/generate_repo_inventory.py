#!/usr/bin/env python3
"""Generate a machine-readable repository inventory snapshot.

Outputs ``artifacts/proof/repo_inventory.json`` with counts of adapters,
routes, tests, migrations, enabled sources, and stub adapters.  Intended to
be re-run after any significant structural change so the proof artifacts stay
current.

Usage::

    python scripts/generate_repo_inventory.py           # writes artifact
    python scripts/generate_repo_inventory.py --print   # also prints JSON

"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _count_adapter_registry() -> int:
    """Count keys in ADAPTER_REGISTRY via AST (no import needed)."""
    init_path = REPO_ROOT / "backend" / "app" / "ingestion" / "source_adapters" / "__init__.py"
    tree = ast.parse(init_path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        # Handle both plain assignment and annotated assignment
        # (``ADAPTER_REGISTRY: dict[str, type] = {...}`` is an AnnAssign)
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "ADAPTER_REGISTRY":
                if node.value and isinstance(node.value, ast.Dict):
                    return len(node.value.keys)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "ADAPTER_REGISTRY":
                    if isinstance(node.value, ast.Dict):
                        return len(node.value.keys)
    raise RuntimeError("ADAPTER_REGISTRY not found in source_adapters/__init__.py")


def _count_stub_adapters() -> int:
    """Count adapter classes that raise NotImplementedError in their fetch() method."""
    adapters_dir = REPO_ROOT / "backend" / "app" / "ingestion" / "source_adapters"
    count = 0
    for py_file in sorted(adapters_dir.glob("*.py")):
        if py_file.name == "__init__.py":
            continue
        src = py_file.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if node.name == "fetch":
                    for stmt in ast.walk(node):
                        if isinstance(stmt, ast.Raise):
                            if stmt.exc and isinstance(stmt.exc, ast.Call):
                                if isinstance(stmt.exc.func, ast.Name):
                                    if stmt.exc.func.id == "NotImplementedError":
                                        count += 1
                                        break
    return count


def _count_routes() -> int:
    """Count HTTP route definitions by scanning for @router.get/post/etc decorators."""
    backend_dir = REPO_ROOT / "backend" / "app"
    count = 0
    verbs = {"get", "post", "put", "patch", "delete", "head", "options"}
    for py_file in backend_dir.rglob("*.py"):
        src = py_file.read_text(encoding="utf-8")
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                        if dec.func.attr in verbs:
                            count += 1
    return count


def _count_tests() -> int:
    """Count test_*.py files in backend/app/tests/."""
    tests_dir = REPO_ROOT / "backend" / "app" / "tests"
    return len(list(tests_dir.glob("test_*.py")))


def _count_migrations() -> int:
    """Count Alembic version files in backend/alembic/versions/."""
    versions_dir = REPO_ROOT / "backend" / "alembic" / "versions"
    if not versions_dir.exists():
        return 0
    return len(list(versions_dir.glob("*.py")))


def _count_enabled_sources() -> int:
    """Count sources with automation_status == 'machine_ready' in YAML."""
    sources_dir = REPO_ROOT / "backend" / "app" / "ingestion" / "sources"
    if not sources_dir.exists():
        return 0
    count = 0
    for yaml_file in sources_dir.rglob("*.yaml"):
        for line in yaml_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("automation_status:"):
                value = stripped.split(":", 1)[1].strip()
                if value == "machine_ready":
                    count += 1
    return count


def build_inventory() -> dict:
    return {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "adapter_count": _count_adapter_registry(),
        "stub_adapter_count": _count_stub_adapters(),
        "route_count": _count_routes(),
        "test_file_count": _count_tests(),
        "migration_count": _count_migrations(),
        "enabled_source_count": _count_enabled_sources(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--print", dest="print_output", action="store_true",
        help="Print JSON to stdout in addition to writing the artifact.",
    )
    args = parser.parse_args()

    inventory = build_inventory()
    out_path = REPO_ROOT / "artifacts" / "proof" / "repo_inventory.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")

    if args.print_output:
        json.dump(inventory, sys.stdout, indent=2)
        sys.stdout.write("\n")

    print(f"Wrote {out_path.relative_to(REPO_ROOT)}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
