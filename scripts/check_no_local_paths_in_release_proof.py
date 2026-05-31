#!/usr/bin/env python3
"""Fail when release-included proof metadata contains local absolute paths.

This checks the canonical proof metadata files that are included in release
archives and should not leak workstation-specific absolute paths.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


LOCAL_PATH_PATTERNS = (
    re.compile(r"/Users/[^\s\"'`]+"),
    re.compile(r"/home/[^\s\"'`]+"),
    re.compile(r"/private/[^\s\"'`]+"),
    re.compile(r"[A-Za-z]:\\[^\s\"'`]+"),
)


def _find_matches(text: str) -> list[str]:
    matches: list[str] = []
    for pattern in LOCAL_PATH_PATTERNS:
        matches.extend(pattern.findall(text))
    return sorted(set(matches))


def _iter_targets(root: Path) -> list[Path]:
    targets: list[Path] = [root / "CURRENT_PROOF.md"]

    proof_root = root / "artifacts" / "proof" / "current"
    if proof_root.exists():
        for path in sorted(proof_root.rglob("*")):
            if path.is_file() and path.suffix.lower() in {".md", ".json", ".log", ".txt"}:
                targets.append(path)

    docs_root = root / "docs"
    if docs_root.exists():
        for path in sorted(docs_root.rglob("*")):
            if not path.is_file():
                continue
            if "/docs/archive/" in str(path).replace("\\", "/"):
                continue
            if path.suffix.lower() in {".md", ".json", ".txt"}:
                targets.append(path)

    # De-duplicate while preserving deterministic order.
    deduped: dict[Path, None] = {}
    for path in targets:
        deduped[path] = None
    return list(deduped)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    targets = _iter_targets(root)

    violations: list[tuple[Path, list[str]]] = []
    for path in targets:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        matches = _find_matches(text)
        if matches:
            violations.append((path, matches))

    if violations:
        print("LOCAL_PATH_HYGIENE: FAIL")
        for path, matches in violations:
            rel = path.relative_to(root)
            print(f"  {rel}:")
            for value in matches:
                print(f"    {value}")
        return 1

    print("LOCAL_PATH_HYGIENE: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
