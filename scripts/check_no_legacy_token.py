#!/usr/bin/env python3
"""
CI guard: fail if legacy admin token patterns appear in frontend TypeScript files
outside of the explicitly allowlisted locations.

Usage:
    python scripts/check_no_legacy_token.py
Exit code 0 = clean, 1 = violations found.
"""

import re
import sys
from pathlib import Path

# Patterns that indicate use of the legacy x-jta-admin-token mechanism.
PATTERNS = [
    re.compile(r"x-jta-admin-token", re.IGNORECASE),
    re.compile(r"process\.env\.JTA_ADMIN_TOKEN"),
    re.compile(r"JTA_ENABLE_LEGACY_ADMIN_TOKEN"),
]

# Files (relative to the frontend root) that are allowed to reference these patterns
# because they intentionally implement the legacy fallback.
ALLOWLIST = {
    "app/api/admin/_auth.ts",  # Holds the explicit legacy fallback path.
}

FRONTEND_ROOT = Path(__file__).parent.parent / "frontend"


def check() -> int:
    violations: list[str] = []

    for ts_file in sorted(FRONTEND_ROOT.rglob("*.ts")) + sorted(
        FRONTEND_ROOT.rglob("*.tsx")
    ):
        relative = ts_file.relative_to(FRONTEND_ROOT).as_posix()
        if relative in ALLOWLIST:
            continue

        text = ts_file.read_text(encoding="utf-8")
        for pattern in PATTERNS:
            for match in pattern.finditer(text):
                line_no = text[: match.start()].count("\n") + 1
                violations.append(
                    f"{relative}:{line_no}: forbidden pattern '{match.group()}'"
                )

    if violations:
        print("check_no_legacy_token: FAILED — legacy token usage found:")
        for v in violations:
            print(f"  {v}")
        return 1

    print("check_no_legacy_token: OK — no legacy token usage outside allowlist.")
    return 0


if __name__ == "__main__":
    sys.exit(check())
