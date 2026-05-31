#!/usr/bin/env python3
"""Fail when active files drift from canonical release archive naming.

This check enforces the canonical release artifact naming policy:
- archive path: dist/JUDGE_ATLAS-main-final.zip
- archive root: JUDGE_ATLAS-main

It intentionally scans only active sources (scripts, workflows, docs, Makefile,
README) and excludes archived/legacy content.
"""

from __future__ import annotations

import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]

SCAN_GLOBS = (
    "scripts/**/*.py",
    "scripts/**/*.sh",
    ".github/workflows/**/*.yml",
    "docs/**/*.md",
    "README.md",
    "deploy/README.md",
    "Makefile",
)

EXCLUDE_PREFIXES = (
    "docs/archive/",
    "external_reference/",
    "artifacts/",
)

FORBIDDEN_PATTERNS = (
    re.compile(r"dist/JUDGE_ATLASX-main\.clean\.zip"),
    re.compile(r"dist/JUDGE_ATLAS-main\.clean\.zip"),
)


def _iter_files() -> list[Path]:
    files: set[Path] = set()
    for glob in SCAN_GLOBS:
        for path in REPO_ROOT.glob(glob):
            if not path.is_file():
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel.startswith(EXCLUDE_PREFIXES):
                continue
            files.add(path)
    return sorted(files)


def main() -> int:
    violations: list[str] = []

    for path in _iter_files():
        rel = path.relative_to(REPO_ROOT).as_posix()
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in FORBIDDEN_PATTERNS:
            for match in pattern.finditer(text):
                line = text.count("\n", 0, match.start()) + 1
                violations.append(
                    f"forbidden_release_archive_reference:{rel}:{line}:{match.group(0)}"
                )

    if violations:
        print("RELEASE_NAMING_DRIFT: FAIL")
        for violation in violations:
            print(f"- {violation}")
        return 1

    print("RELEASE_NAMING_DRIFT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
