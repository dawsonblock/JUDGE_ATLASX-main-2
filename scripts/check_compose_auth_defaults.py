#!/usr/bin/env python3
"""CI guard: enforce JWT-first auth defaults in docker-compose.

Policy:
- If JTA_ENABLE_LEGACY_ADMIN_TOKEN is false, compose defaults must not require
  JTA_ADMIN_TOKEN or JTA_ADMIN_REVIEW_TOKEN via the :? mandatory env syntax.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

LEGACY_DISABLED_RE = re.compile(
    r"^\s*JTA_ENABLE_LEGACY_ADMIN_TOKEN\s*:\s*[\"']?false[\"']?\s*$",
    re.IGNORECASE | re.MULTILINE,
)
MANDATORY_ADMIN_TOKEN_RE = re.compile(
    r"^\s*JTA_ADMIN_TOKEN\s*:\s*.*:\?.*$",
    re.IGNORECASE | re.MULTILINE,
)
MANDATORY_REVIEW_TOKEN_RE = re.compile(
    r"^\s*JTA_ADMIN_REVIEW_TOKEN\s*:\s*.*:\?.*$",
    re.IGNORECASE | re.MULTILINE,
)


def check(compose_path: Path) -> int:
    if not compose_path.is_file():
        print(f"ERROR: compose file not found: {compose_path}", file=sys.stderr)
        return 2

    text = compose_path.read_text(encoding="utf-8")
    legacy_disabled = bool(LEGACY_DISABLED_RE.search(text))

    violations: list[str] = []
    if legacy_disabled:
        if MANDATORY_ADMIN_TOKEN_RE.search(text):
            violations.append(
                "JTA_ADMIN_TOKEN is mandatory despite legacy token mode being disabled"
            )
        if MANDATORY_REVIEW_TOKEN_RE.search(text):
            violations.append(
                "JTA_ADMIN_REVIEW_TOKEN is mandatory despite legacy token mode being disabled"
            )

    if violations:
        print("check_compose_auth_defaults: FAILED")
        for violation in violations:
            print(f"  - {violation}")
        return 1

    print("check_compose_auth_defaults: OK — compose defaults are JWT-first compatible.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--compose",
        default="docker-compose.yml",
        help="Path to docker-compose file to validate",
    )
    args = parser.parse_args()
    return check(Path(args.compose))


if __name__ == "__main__":
    sys.exit(main())
