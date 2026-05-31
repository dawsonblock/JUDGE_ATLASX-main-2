#!/usr/bin/env python3
"""Validate required Python/Node toolchain versions for proof and release gates."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _run_version(command: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(command, capture_output=True, text=True, check=False)
    except FileNotFoundError:
        return 127, "missing"
    output = (proc.stdout or proc.stderr or "").strip()
    return proc.returncode, output


def _major(version: str) -> int | None:
    text = version.strip().lstrip("v")
    if not text:
        return None
    head = text.split(".", 1)[0]
    if not head.isdigit():
        return None
    return int(head)


def _python_mm(version_info: tuple[int, int, int]) -> str:
    return f"{version_info[0]}.{version_info[1]}.{version_info[2]}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(REPO_ROOT), help="Repository root")
    parser.add_argument(
        "--expected-python-major",
        type=int,
        default=3,
        help="Expected Python major version",
    )
    parser.add_argument(
        "--expected-python-minor",
        type=int,
        default=11,
        help="Expected Python minor version",
    )
    parser.add_argument(
        "--expected-node-major",
        type=int,
        default=22,
        help="Expected Node major version",
    )
    args = parser.parse_args()

    repo_root = Path(args.root).resolve()
    python_version = _python_mm((sys.version_info.major, sys.version_info.minor, sys.version_info.micro))

    node_code, node_version = _run_version(["node", "--version"])
    npm_code, npm_version = _run_version(["npm", "--version"])
    pnpm_code, pnpm_version = _run_version(["pnpm", "--version"])

    failures: list[str] = []

    if (sys.version_info.major, sys.version_info.minor) != (
        args.expected_python_major,
        args.expected_python_minor,
    ):
        failures.append(
            "python_version_mismatch:"
            f"expected={args.expected_python_major}.{args.expected_python_minor}:actual={python_version}"
        )

    if node_code != 0:
        failures.append(f"node_unavailable:{node_version or 'missing'}")
    else:
        node_major = _major(node_version)
        if node_major is None:
            failures.append(f"node_version_unparseable:{node_version}")
        elif node_major != args.expected_node_major:
            failures.append(
                f"node_major_mismatch:expected={args.expected_node_major}:actual={node_major}:version={node_version}"
            )

    if npm_code != 0:
        failures.append(f"npm_unavailable:{npm_version or 'missing'}")

    print(f"TOOLCHAIN_ROOT: {repo_root}")
    print(f"PYTHON_VERSION: {python_version}")
    print(f"NODE_VERSION: {node_version if node_code == 0 else 'unavailable'}")
    print(f"NPM_VERSION: {npm_version if npm_code == 0 else 'unavailable'}")
    print(f"PNPM_VERSION: {pnpm_version if pnpm_code == 0 else 'not-installed'}")

    if failures:
        print(f"TOOLCHAIN_CHECK: FAIL ({len(failures)} issue(s))")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("TOOLCHAIN_CHECK: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
