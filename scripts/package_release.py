#!/usr/bin/env python3
"""Build the canonical alpha proof release archive.

Default output:
  dist/JUDGE_ATLASX-alpha-proof.zip
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = REPO_ROOT / "dist" / "JUDGE_ATLASX-alpha-proof.zip"
DEFAULT_ROOT = "JUDGE_ATLAS-main"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Output archive path")
    parser.add_argument(
        "--root-name",
        default=DEFAULT_ROOT,
        help="Archive top-level root directory name",
    )
    parser.add_argument(
        "--include-external",
        action="store_true",
        help="Include external paths (disabled by default)",
    )
    parser.add_argument(
        "--include-proof-archive",
        action="store_true",
        help="Include proof archive history (disabled by default)",
    )
    args = parser.parse_args()

    cmd = [
        sys.executable,
        "scripts/build_release_archive.py",
        "--output",
        args.output,
        "--root-name",
        args.root_name,
    ]
    if args.include_external:
        cmd.append("--include-external")
    if args.include_proof_archive:
        cmd.append("--include-proof-archive")

    cp = subprocess.run(cmd, cwd=REPO_ROOT, check=False)
    return cp.returncode


if __name__ == "__main__":
    raise SystemExit(main())
