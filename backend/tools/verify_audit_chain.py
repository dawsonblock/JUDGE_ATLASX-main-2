"""Verify persisted audit-chain integrity.

Usage:
    python -m backend.tools.verify_audit_chain
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Ensure the backend directory is importable as top-level `app` when running
# `python -m backend.tools.*` from repository root.
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.db.session import SessionLocal
from app.audit.integrity_chain import verify_chain


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify persisted audit-chain integrity")
    parser.add_argument("--allow-empty", action="store_true")
    args = parser.parse_args(sys.argv[1:])

    try:
        with SessionLocal() as db:
            result = verify_chain(db)
    except Exception as exc:  # pragma: no cover - defensive
        if args.allow_empty and "no such table" in str(exc).lower():
            print("AUDIT CHAIN VERIFICATION")
            print("entries_checked=0")
            print("chain_head=EMPTY")
            print("violations=0")
            print("RESULT: PASS allow_empty")
            return 0
        print("AUDIT CHAIN VERIFICATION")
        print("entries_checked=0")
        print(f"RESULT: FAIL database_error={exc.__class__.__name__}")
        print(str(exc))
        return 1

    print("AUDIT CHAIN VERIFICATION")
    print(f"entries_checked={result.entries_checked}")
    print(f"chain_head={result.chain_head or 'EMPTY'}")
    print(f"violations={len(result.violations)}")

    if args.allow_empty and result.entries_checked == 0:
        print("RESULT: PASS allow_empty")
        return 0

    if result.ok:
        print("RESULT: PASS")
        return 0

    for err in result.violations:
        print(f"- {err}")
    print("RESULT: FAIL audit_chain_violation")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
