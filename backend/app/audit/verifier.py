"""CLI-callable chain verifier; exits non-zero on any violation."""
from __future__ import annotations

import sys


def main() -> None:
    from app.db.session import SessionLocal
    from app.audit.integrity_chain import verify_chain

    with SessionLocal() as db:
        result = verify_chain(db)

    if result.entries_checked == 0:
        print("audit_chain: no entries (empty log)")
        sys.exit(0)

    if result.ok:
        print(
            f"audit_chain: OK — {result.entries_checked} entries, head={result.chain_head[:16]}..."
        )
        sys.exit(0)
    else:
        print(f"audit_chain: FAIL — {len(result.violations)} violation(s):")
        for v in result.violations:
            print(f"  - {v}")
        sys.exit(1)


if __name__ == "__main__":
    main()
