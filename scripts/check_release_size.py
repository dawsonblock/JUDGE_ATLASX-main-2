#!/usr/bin/env python3
"""Check release size to prevent bloat."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Maximum release size in bytes (100 MB)
MAX_RELEASE_SIZE = 100 * 1024 * 1024


def main() -> int:
    """Check release size against threshold."""
    # Check if release artifacts exist
    artifacts_dir = REPO_ROOT / "artifacts" / "current"
    if not artifacts_dir.exists():
        print("Release artifacts not found, skipping size check")
        return 0

    # Calculate total size
    total_size = 0
    for item in artifacts_dir.rglob("*"):
        if item.is_file():
            total_size += item.stat().st_size

    size_mb = total_size / (1024 * 1024)
    print(f"release_size_mb={size_mb:.2f}")
    print(f"max_size_mb={MAX_RELEASE_SIZE / (1024 * 1024):.2f}")

    if total_size > MAX_RELEASE_SIZE:
        print(f"Release size {size_mb:.2f}MB exceeds maximum {MAX_RELEASE_SIZE / (1024 * 1024):.2f}MB")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
