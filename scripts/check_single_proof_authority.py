#!/usr/bin/env python3
"""Fail if proof authority exists outside canonical artifacts/proof/current."""

from __future__ import annotations

import argparse
from pathlib import Path

CANONICAL_DIR = Path("artifacts/proof/current")
LEGACY_DIRS = (
    Path("artifacts/current"),
    Path("artifacts/proof/backend"),
    Path("artifacts/proof/frontend"),
    Path("artifacts/proof/latest"),
    Path("proof/latest"),
)
LEGACY_FILES = (
    Path("artifacts/proof/source_registry_status.json"),
)


def _has_active_files(path: Path) -> bool:
    if not path.exists():
        return False
    if path.is_file():
        return True

    for item in path.rglob("*"):
        if not item.is_file():
            continue
        if item.name in {".gitkeep", ".keep", "README.md"}:
            continue
        return True
    return False


def check(root: Path) -> list[str]:
    errors: list[str] = []

    for rel in LEGACY_DIRS:
        absolute = root / rel
        if _has_active_files(absolute):
            errors.append(
                f"legacy proof directory contains active artifacts: {rel}"
            )

    for rel in LEGACY_FILES:
        absolute = root / rel
        if absolute.is_file():
            errors.append(
                "legacy proof artifact present outside canonical current: "
                f"{rel}"
            )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="repository root")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    errors = check(root)

    if errors:
        print("single_proof_authority: FAIL")
        for error in errors:
            print(f" - {error}")
        return 1

    print("single_proof_authority: PASS")
    print("canonical authority: artifacts/proof/current")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
