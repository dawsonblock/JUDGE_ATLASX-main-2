#!/usr/bin/env python3
"""CI guard: no hardcoded source key strings outside of app/ingestion/source_keys.py.

Scans all .py files under backend/app and fails if any file other than
source_keys.py contains a bare string literal that matches a canonical
source key.

The enforced key set is derived at runtime from
``backend/app/ingestion/source_keys.py`` so this script never drifts out
of sync with the actual registry.

Usage:
    python scripts/check_source_keys.py
    python scripts/check_source_keys.py --root backend/app
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import sys
from pathlib import Path


def _load_canonical_keys(repo_root: Path) -> frozenset[str]:
    """Import source_keys.py at runtime and return CANONICAL_SOURCE_KEYS."""
    module_path = repo_root / "backend" / "app" / "ingestion" / "source_keys.py"
    if not module_path.is_file():
        print(
            f"ERROR: could not find source_keys.py at {module_path}",
            file=sys.stderr,
        )
        sys.exit(2)
    spec = importlib.util.spec_from_file_location("source_keys", module_path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return frozenset(mod.CANONICAL_SOURCE_KEYS)  # type: ignore[attr-defined]

_ALLOWED_SUFFIXES = {
    "source_keys.py",
}

_TEST_DIR_PARTS = {"tests", "test"}


def _is_allowed_path(path: Path) -> bool:
    if path.name in _ALLOWED_SUFFIXES:
        return True
    if any(part in _TEST_DIR_PARTS for part in path.parts):
        return True
    return False


def _string_literals(tree: ast.AST) -> list[tuple[int, str]]:
    results: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            results.append((node.lineno, node.value))
    return results


def check(root: Path, canonical_keys: frozenset[str]) -> int:
    violations: list[str] = []
    for py_file in root.rglob("*.py"):
        if _is_allowed_path(py_file):
            continue
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))
        except SyntaxError:
            continue
        for lineno, value in _string_literals(tree):
            if value in canonical_keys:
                violations.append(f"{py_file}:{lineno}: hardcoded source key {value!r}")
    if violations:
        print(
            "ERROR: hardcoded source key strings detected (use resolve_source_key()):"
        )
        for v in violations:
            print(f"  {v}")
        return 1
    print(f"OK: no hardcoded source key strings in {root}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default="backend/app",
        help="Directory to scan (default: backend/app)",
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repo root for locating source_keys.py (default: .)",
    )
    args = parser.parse_args()
    root = Path(args.root)
    repo_root = Path(args.repo_root)
    if not root.is_dir():
        print(f"ERROR: {root} is not a directory", file=sys.stderr)
        sys.exit(2)
    canonical_keys = _load_canonical_keys(repo_root)
    sys.exit(check(root, canonical_keys))


if __name__ == "__main__":
    main()
