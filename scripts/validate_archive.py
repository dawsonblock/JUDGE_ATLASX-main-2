#!/usr/bin/env python3
"""Compatibility wrapper for release archive validation.

Usage:
  python scripts/validate_archive.py <archive_path>
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", help="Path to release archive")
    parser.add_argument(
        "--expected-root",
        default="JUDGE_ATLAS-main",
        help="Expected top-level root directory in zip",
    )
    parser.add_argument(
        "--allow-external",
        action="store_true",
        help="Allow external paths in archive",
    )
    args = parser.parse_args()

    cmd = [
        sys.executable,
        "scripts/validate_release_archive.py",
        "--archive",
        args.archive,
        "--expected-root",
        args.expected_root,
    ]
    if args.allow_external:
        cmd.append("--allow-external")

    cp = subprocess.run(cmd, cwd=REPO_ROOT, check=False)
    return cp.returncode


if __name__ == "__main__":
    raise SystemExit(main())
