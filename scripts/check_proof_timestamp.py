#!/usr/bin/env python3
"""Check proof timestamp freshness to prevent stale artifacts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROOF_DIR = REPO_ROOT / "artifacts" / "current"

# Maximum proof age in hours (24 hours)
MAX_PROOF_AGE_HOURS = 24


def main() -> int:
    """Check proof timestamp freshness."""
    manifest_file = PROOF_DIR / "PROOF_MANIFEST.json"
    if not manifest_file.exists():
        print("Proof manifest not found, skipping timestamp check")
        return 0

    with open(manifest_file) as f:
        manifest = json.load(f)

    generated_at = manifest.get("generated_at_utc")
    if not generated_at:
        print("Proof manifest missing generated_at_utc")
        return 1

    try:
        proof_time = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        age_hours = (now - proof_time).total_seconds() / 3600

        print(f"proof_age_hours={age_hours:.2f}")
        print(f"max_age_hours={MAX_PROOF_AGE_HOURS}")

        if age_hours > MAX_PROOF_AGE_HOURS:
            print(f"Proof is {age_hours:.2f} hours old, exceeds maximum {MAX_PROOF_AGE_HOURS} hours")
            return 1

        return 0
    except (ValueError, TypeError) as e:
        print(f"Failed to parse proof timestamp: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
