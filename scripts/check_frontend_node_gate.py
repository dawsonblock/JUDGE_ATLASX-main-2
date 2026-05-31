#!/usr/bin/env python3
"""Fail-closed Node version gate for frontend proof.

Expected behavior:
- PASS only when Node major version matches required version
- Emit clear mismatch message for proof logs
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys


def _parse_major_minor(node_version: str) -> tuple[int, int] | None:
    match = re.match(r"^v?(\d+)\.(\d+)", node_version.strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def main() -> int:
    parser = argparse.ArgumentParser(description="Frontend Node version gate")
    parser.add_argument("--expected-major", type=int, default=22)
    args = parser.parse_args()

    proc = subprocess.run(
        ["node", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        print("Node executable not available")
        return 1

    version = proc.stdout.strip() or "unknown"
    parsed = _parse_major_minor(version)
    if parsed is None:
        print(f"Unable to parse Node version: {version}")
        return 1

    major, minor = parsed
    if major != args.expected_major:
        expected = f"{args.expected_major}.x"
        print(f"NODE_VERSION: {version}")
        print(f"Frontend release gate requires Node {expected}. Current Node: {version}. Use nvm use {args.expected_major}.")
        return 1

    npm_proc = subprocess.run(
        ["npm", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    npm_version = npm_proc.stdout.strip() if npm_proc.returncode == 0 else "unknown"

    print(f"NODE_VERSION: {version}")
    print(f"NPM_VERSION: {npm_version}")
    print(f"Node gate PASS: {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
