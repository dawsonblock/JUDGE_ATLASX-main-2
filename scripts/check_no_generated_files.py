#!/usr/bin/env python3
"""CI guard: fail if generated/cache files are committed to the repository.

Checks for patterns that must not be committed:
  - __pycache__/ directories with .pyc/.pyo files
  - .pytest_cache/ directories
  - .mypy_cache/ directories
  - node_modules/ directories
  - .next/ build output
  - dist/ build output
  - build/ build output
  - artifacts/proof/temp/ temp artifacts
  - *.egg-info/ directories

Usage:
    python scripts/check_no_generated_files.py [--root PATH]

Exits 1 if any prohibited generated files are found.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


# Patterns of committed files that must not exist.
# Each entry is a tuple of (description, glob_pattern_relative_to_root).
PROHIBITED_PATTERNS: list[tuple[str, str]] = [
    ("Python bytecode (.pyc)", "**/*.pyc"),
    ("Python bytecode (.pyo)", "**/*.pyo"),
    ("coverage data", "**/.coverage"),
    ("Python bytecode dir", "**/__pycache__"),
    ("pytest cache", "**/.pytest_cache"),
    ("mypy cache", "**/.mypy_cache"),
    ("npm modules", "**/node_modules"),
    ("Next.js build", "**/.next"),
    ("dist build output", "**/dist"),
    ("build output", "**/build"),
    ("egg-info", "**/*.egg-info"),
    ("proof temp artifacts", "**/artifacts/proof/temp"),
]

# Directory path-part names that must never be committed
_PROHIBITED_DIR_NAMES: frozenset[str] = frozenset({
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    "node_modules",
    ".next",
    "dist",
    "build",
})

# Directories to always skip when walking
SKIP_DIRS: frozenset[str] = frozenset({
    ".git",
    ".venv",
    "venv",
    ".nox",
    ".tox",
    "research",
    "external",
    "external_reference",
    "docs/archive",
})


def _matches_prohibited(filepath: str) -> str | None:
    """Return a violation label if *filepath* matches a prohibited pattern, else None.

    Matches:
    - Any path component that is a prohibited directory name (dist, build, __pycache__, …)
    - Any path component ending with ``.egg-info``
    - Files ending with ``.pyc`` or ``.pyo``
    - Paths containing the ``artifacts/proof/temp`` segment sequence
    """
    p = Path(filepath)
    parts = p.parts

    # Check each path component for prohibited directory names / egg-info
    for part in parts:
        if part in _PROHIBITED_DIR_NAMES:
            return f"[{part}]"
        if part.endswith(".egg-info"):
            return "[egg-info]"

    # Check file extension for compiled Python bytecode
    if p.name.endswith(".pyc") or p.name.endswith(".pyo"):
        return "[Python bytecode]"

    # Coverage output must never be committed.
    if p.name == ".coverage":
        return "[coverage data]"

    # Check for the exact artifacts/proof/temp directory sequence anywhere in the path
    for i in range(len(parts) - 2):
        if parts[i] == "artifacts" and parts[i + 1] == "proof" and parts[i + 2] == "temp":
            return "[proof temp artifacts]"

    return None


def check_committed_generated_files(root: Path) -> list[str]:
    """Return a list of committed generated files that should not be in the repo."""
    violations: list[str] = []

    # Use git ls-files to check tracked files
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=str(root),
            capture_output=True,
            text=True,
            check=True,
        )
        tracked_files = set(result.stdout.strip().split("\n"))
    except (subprocess.CalledProcessError, FileNotFoundError):
        # If git is not available, fall back to filesystem scan
        print("WARNING: git not available, using filesystem scan", file=sys.stderr)
        tracked_files = None

    if tracked_files is not None:
        for filepath in tracked_files:
            if not filepath:
                continue
            path_obj = Path(filepath)
            parts = path_obj.parts
            if any(part in SKIP_DIRS for part in parts):
                continue
            if filepath.startswith("docs/archive/"):
                continue
            label = _matches_prohibited(filepath)
            if label:
                violations.append(f"{label} {filepath}")
    else:
        # Filesystem scan fallback
        for desc, glob_pattern in PROHIBITED_PATTERNS:
            for match in root.glob(glob_pattern):
                # Skip .git, .venv, etc.
                parts = match.relative_to(root).parts
                if any(p in SKIP_DIRS for p in parts):
                    continue
                violations.append(f"[{desc}] {match.relative_to(root)}")

    return sorted(set(violations))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root to scan (default: current directory)",
    )
    args = parser.parse_args()
    root = Path(args.root).resolve()

    print(f"Checking for committed generated files in: {root}")
    violations = check_committed_generated_files(root)

    if violations:
        print(f"\n❌  FAIL: {len(violations)} committed generated file(s) found:\n")
        for v in violations:
            print(f"  {v}")
        print(
            "\nThese files must be removed from git tracking and added to .gitignore.\n"
            "Run: git rm -r --cached <path>"
        )
        return 1

    print(f"✅  PASS: No committed generated files found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
