#!/usr/bin/env python3
"""CI guard: fail if any repository path component contains whitespace or control characters.

Walks the repository, skipping generated/dependency/reference trees (including
external_reference/), and reports
any path components that contain whitespace (spaces, tabs, newlines) or ASCII
control characters (0x00–0x1F, 0x7F). Such paths cause double-directory bugs
under git and platform-specific inconsistencies.

Usage:
    python scripts/check_path_hygiene.py [--root PATH]

Exits 1 if any path hygiene violations are found.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


SKIP_DIRS: frozenset[str] = frozenset({
    ".git",
    "research",
    "external",
    "external_reference",
    ".venv",
    "venv",
    ".nox",
    ".tox",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
})

# Match whitespace chars plus DEL (0x7F) and other ASCII control chars (0x00–0x1F)
_BAD_CHARS = re.compile(r"[\x00-\x1f\x7f\s]")


def _has_bad_chars(name: str) -> bool:
    return bool(_BAD_CHARS.search(name))


def scan_repo(root: Path) -> list[str]:
    """Return list of relative path strings that violate path hygiene."""
    violations: list[str] = []

    def _walk(directory: Path, rel_parts: tuple[str, ...]) -> None:
        try:
            entries = sorted(directory.iterdir(), key=lambda e: e.name)
        except PermissionError:
            return

        for entry in entries:
            child_parts = rel_parts + (entry.name,)
            rel_str = "/".join(child_parts)

            if _has_bad_chars(entry.name):
                violations.append(rel_str)

            if entry.is_dir() and not entry.is_symlink():
                if entry.name in SKIP_DIRS:
                    continue
                _walk(entry, child_parts)

    _walk(root, ())
    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root to scan (default: current directory)",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"[check_path_hygiene] ERROR: root is not a directory: {root}", file=sys.stderr)
        return 1

    violations = scan_repo(root)

    if violations:
        print(
            f"[check_path_hygiene] FAIL: {len(violations)} path hygiene violation(s) — "
            "whitespace or control characters in path components:"
        )
        for v in violations:
            print(f"  - {v!r}")
        return 1

    print(f"[check_path_hygiene] PASS: no path hygiene violations in {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
