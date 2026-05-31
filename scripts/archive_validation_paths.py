#!/usr/bin/env python3
"""Helpers for locating the JUDGE-main root inside extracted archives."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def candidate_repo_roots(extract_dir: Path) -> list[Path]:
    """Find repository roots by looking for scripts/release_gate.py."""
    candidates: list[Path] = []
    for marker in extract_dir.glob("**/scripts/release_gate.py"):
        repo_root = marker.parents[1]
        if repo_root.is_dir():
            candidates.append(repo_root)

    unique_candidates: list[Path] = []
    seen: set[Path] = set()
    for candidate in sorted(candidates):
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_candidates.append(candidate)
    return unique_candidates


def resolve_repo_root(extract_dir: Path) -> Path:
    if not extract_dir.is_dir():
        raise FileNotFoundError(f"extract directory does not exist: {extract_dir}")

    candidates = candidate_repo_roots(extract_dir)
    if not candidates:
        raise FileNotFoundError(
            f"could not locate repository root under extracted archive root: {extract_dir}"
        )
    if len(candidates) > 1:
        raise RuntimeError(
            "multiple repository roots found: "
            + ", ".join(str(candidate) for candidate in candidates)
        )
    return candidates[0]


def candidate_judge_main_roots(extract_dir: Path) -> list[Path]:
    candidates: list[Path] = []

    direct = extract_dir / "JUDGE-main"
    if direct.is_dir():
        candidates.append(direct)

    for child in sorted(extract_dir.iterdir()):
        if not child.is_dir():
            continue
        nested = child / "JUDGE-main"
        if nested.is_dir():
            candidates.append(nested)

    unique_candidates: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        unique_candidates.append(candidate)

    return unique_candidates


def resolve_judge_main_root(extract_dir: Path) -> Path:
    # Backward-compatible alias used by existing scripts.
    return resolve_repo_root(extract_dir)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--extract-dir",
        required=True,
        help="Directory containing the extracted archive contents",
    )
    args = parser.parse_args(argv)

    try:
        resolved = resolve_judge_main_root(Path(args.extract_dir).resolve())
    except (FileNotFoundError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print(str(resolved))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())