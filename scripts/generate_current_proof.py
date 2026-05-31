#!/usr/bin/env python3
"""Generate canonical current-proof artifacts from executable checks only.

This entrypoint runs the release gate and then verifies the three core proof
consistency checks. It exists as the single Phase-1 proof generation command.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _run(cmd: list[str], repo_root: Path) -> int:
    cp = subprocess.run(cmd, cwd=repo_root, check=False)
    return cp.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root")
    args = parser.parse_args()

    repo_root = Path(args.root).resolve()

    steps: list[tuple[str, list[str]]] = [
        ("release_gate", [sys.executable, "scripts/release_gate.py"]),
        ("proof_consistency", [sys.executable, "scripts/check_proof_consistency.py"]),
        ("proof_freshness", [sys.executable, "scripts/check_proof_freshness.py"]),
        (
            "required_proof_logs",
            [
                sys.executable,
                "scripts/check_required_proof_logs.py",
                "--strict-required-files",
            ],
        ),
    ]

    failures: list[str] = []
    for name, cmd in steps:
        rc = _run(cmd, repo_root)
        if rc != 0:
            failures.append(f"{name}(rc={rc})")

    if failures:
        print("GENERATE_CURRENT_PROOF: FAIL")
        for failure in failures:
            print(f"- {failure}")
        return 1

    print("GENERATE_CURRENT_PROOF: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
