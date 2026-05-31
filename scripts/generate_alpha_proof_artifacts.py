#!/usr/bin/env python3
"""Generate canonical proof sidecars from release gate output."""

from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE_JSON = REPO_ROOT / "artifacts" / "proof" / "current" / "release_gate.json"
GATE_MANIFEST = REPO_ROOT / "artifacts" / "proof" / "current" / "proof_manifest.json"
OUT_DIR = REPO_ROOT / "artifacts" / "proof" / "current"
OUT_REPORT = OUT_DIR / "PROOF_REPORT.md"
OUT_MANIFEST = OUT_DIR / "RELEASE_MANIFEST.json"


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not GATE_JSON.exists() or not GATE_MANIFEST.exists():
        print("missing release gate artifacts; run scripts/release_gate.py first")
        return 1

    gate_payload = json.loads(GATE_JSON.read_text(encoding="utf-8"))
    manifest_payload = json.loads(GATE_MANIFEST.read_text(encoding="utf-8"))

    checks = gate_payload.get("checks", [])
    failed = [c for c in checks if c.get("status") != "PASS" and c.get("required", True)]
    warnings = [c for c in checks if c.get("status") == "BLOCKED" or c.get("status") == "WARN"]

    covered_dirs = ["backend", "frontend", "scripts", "docs", "artifacts/proof/current"]
    excluded_dirs = [
        "external_reference",
        "artifacts/old",
        "artifacts/archive",
        "generated_logs",
        "tmp",
        "cache",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        ".next",
        "dist",
        "coverage",
    ]

    proof_hash = _hash_bytes((GATE_JSON.read_bytes() + GATE_MANIFEST.read_bytes()))

    out_manifest_payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "release_mode": "alpha",
        "environment": manifest_payload.get("environment", {}),
        "git_commit": manifest_payload.get("git", {}).get("commit", "unknown"),
        "checks_total": len(checks),
        "checks_failed": len(failed),
        "checks_warnings": len(warnings),
        "covered_directories": covered_dirs,
        "excluded_directories": excluded_dirs,
        "proof_hash": proof_hash,
        "source": {
            "release_gate": str(GATE_JSON.relative_to(REPO_ROOT)),
            "proof_manifest": str(GATE_MANIFEST.relative_to(REPO_ROOT)),
        },
        "alpha_limitations": [
            "alpha release only; not production legal authority",
            "evidence is authoritative; AI and memory outputs are derivative",
            "publication requires review + linked evidence snapshot",
        ],
    }

    OUT_MANIFEST.write_text(json.dumps(out_manifest_payload, indent=2) + "\n", encoding="utf-8")

    report_lines = [
        "# Alpha Proof Report",
        "",
        f"- Generated: {out_manifest_payload['generated_at']}",
        f"- Release mode: {out_manifest_payload['release_mode']}",
        f"- Git commit: {out_manifest_payload['git_commit']}",
        f"- Environment: {out_manifest_payload['environment']}",
        f"- Covered directories: {', '.join(covered_dirs)}",
        f"- Excluded directories: {', '.join(excluded_dirs)}",
        f"- Number of checks run: {len(checks)}",
        f"- Failures: {len(failed)}",
        f"- Warnings: {len(warnings)}",
        f"- Proof hash: {proof_hash}",
        "",
        "## Alpha Limitations",
        "",
        "- This report does not claim production readiness.",
        "- This is an evidence-governed alpha release with strict review and publication gates.",
        "- Operational assumptions and proofs are constrained to the covered directories and checks.",
    ]

    OUT_REPORT.write_text("\n".join(report_lines) + "\n", encoding="utf-8")

    print(f"wrote {OUT_REPORT}")
    print(f"wrote {OUT_MANIFEST}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
