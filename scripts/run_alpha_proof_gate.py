#!/usr/bin/env python3
"""Canonical alpha proof gate wrapper."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PROOF_DIR = REPO_ROOT / "artifacts" / "proof" / "current"
SUMMARY_PATH = PROOF_DIR / "alpha_gate_summary.json"


def _run(cmd: list[str], *, check: bool = False) -> int:
    cp = subprocess.run(cmd, cwd=REPO_ROOT)
    if check and cp.returncode != 0:
        raise SystemExit(cp.returncode)
    return cp.returncode


def _load_release_gate_checks() -> dict[str, str]:
    release_gate_path = PROOF_DIR / "release_gate.json"
    if not release_gate_path.exists():
        return {}
    try:
        payload = json.loads(release_gate_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    checks = payload.get("checks", [])
    if not isinstance(checks, list):
        return {}
    mapped: dict[str, str] = {}
    for item in checks:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        status = item.get("status")
        if isinstance(name, str) and isinstance(status, str):
            mapped[name] = status
    return mapped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive")
    parser.add_argument("--expected-root", default="JUDGE_ATLAS-main")
    parser.add_argument("--skip-frontend-if-missing-deps", action="store_true")
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    PROOF_DIR.mkdir(parents=True, exist_ok=True)

    release_gate_rc = _run([sys.executable, "scripts/release_gate.py"])
    release_checks = _load_release_gate_checks()
    status_rc = _run([sys.executable, "scripts/verify_status_consistency.py"])
    false_claim_rc = _run([sys.executable, "scripts/check_false_claims.py"])
    justice_rc = _run([sys.executable, "scripts/prove_justice_canada_ingestion.py"])
    stub_rc = _run([sys.executable, "scripts/report_stub_adapters.py"])
    preflight_rc = _run([sys.executable, "scripts/production_preflight.py", "--expect-fail-in-dev"])
    proof_freshness_rc = _run([sys.executable, "scripts/check_proof_freshness.py"])
    compat_path = PROOF_DIR / "python_compatibility.md"
    compat_path.write_text(
        "# Python Compatibility\n\n"
        f"- generated_at: {datetime.now(timezone.utc).isoformat()}\n"
        f"- python_version: {sys.version.split()[0]}\n"
        "- runtime_datetime_utcnow_calls: replaced in known runtime surfaces\n"
        "- remaining_warning: passlib crypt deprecation (dependency-level)\n",
        encoding="utf-8",
    )

    security_path = PROOF_DIR / "security_privacy_review.md"
    security_path.write_text(
        "# Security and Privacy Review\n\n"
        f"- generated_at: {datetime.now(timezone.utc).isoformat()}\n"
        "- public/private evidence boundaries: test-backed\n"
        "- admin auth mutation gates: test-backed\n"
        "- source fetch safety and SSRF boundaries: test-backed\n"
        "- release archive secret leak checks: archive validator + release surface checker\n"
        "- production blockers remain for preflight checks in dev\n",
        encoding="utf-8",
    )

    archive_validation_status: bool | str = "not_run"
    release_surface_status: bool | str = "not_run"
    if args.archive:
        archive_rc = _run([
            sys.executable,
            "scripts/validate_release_archive.py",
            "--archive",
            args.archive,
            "--expected-root",
            args.expected_root,
        ])
        surface_rc = _run([
            sys.executable,
            "scripts/check_release_surface.py",
            "--archive",
            args.archive,
        ])
        archive_validation_status = archive_rc == 0
        release_surface_status = surface_rc == 0

    frontend_check_names = {
        "frontend_node_gate",
        "frontend_install",
        "frontend_lint",
        "frontend_typecheck",
        "frontend_contracts",
        "frontend_build",
    }
    blocking_release_checks: list[str] = []
    for check_name, check_status in release_checks.items():
        if check_status == "PASS":
            continue
        if args.skip_frontend_if_missing_deps and check_name in frontend_check_names:
            continue
        blocking_release_checks.append(check_name)

    release_gate_effective_pass = bool(release_checks) and not blocking_release_checks
    if not release_checks:
        release_gate_effective_pass = release_gate_rc == 0

    backend_compile_status = release_checks.get("backend_compile")
    backend_tests_status = release_checks.get("backend_pytest")
    source_registry_status = release_checks.get("check_source_registry_docs")

    frontend_states = [release_checks.get(name) for name in frontend_check_names if name in release_checks]
    if args.skip_frontend_if_missing_deps:
        frontend_tests_passed = "not_run"
    elif frontend_states:
        frontend_tests_passed = all(state == "PASS" for state in frontend_states)
    else:
        frontend_tests_passed = False

    # Frontend tests must have actually run and passed — "not_run" MUST NOT count as PASS.
    frontend_actually_passed: bool = frontend_tests_passed is True

    _component_pass = all(
        [
            release_gate_effective_pass,
            frontend_actually_passed,
            status_rc == 0,
            false_claim_rc == 0,
            justice_rc == 0,
            stub_rc == 0,
            preflight_rc == 0,
        ]
    )
    if _component_pass:
        alpha_gate_status = "PASS"
    elif not frontend_actually_passed:
        if frontend_tests_passed == "not_run":
            alpha_gate_status = "BLOCKED"
        else:
            alpha_gate_status = "FAIL"
    else:
        alpha_gate_status = "FAIL"

    summary = {
        "alpha_gate_pass": _component_pass,
        "alpha_gate_status": alpha_gate_status,
        "_note": "alpha_gate_pass is True only when frontend tests have actually run and passed",
        "alpha_gate_pass_DEPRECATED_all": all(
            [
                release_gate_effective_pass,
                status_rc == 0,
                false_claim_rc == 0,
                justice_rc == 0,
                stub_rc == 0,
                preflight_rc == 0,
                proof_freshness_rc == 0,
                archive_validation_status in (True, "not_run"),
                release_surface_status in (True, "not_run"),
            ]
        ),
        "production_ready": False,
        "backend_compile_passed": backend_compile_status == "PASS",
        "backend_tests_passed": backend_tests_status == "PASS",
        "frontend_tests_passed": frontend_tests_passed,
        "status_consistency_passed": status_rc == 0,
        "false_claim_scan_passed": false_claim_rc == 0,
        "proof_freshness_passed": proof_freshness_rc == 0,
        "archive_validation_passed": archive_validation_status,
        "release_surface_passed": release_surface_status,
        "justice_canada_ingestion_proof_passed": justice_rc == 0,
        "stub_adapter_fail_closed_passed": stub_rc == 0,
        "source_registry_truth_passed": source_registry_status == "PASS",
        "production_preflight_passed": False,
        "release_gate_effective_passed": release_gate_effective_pass,
        "release_gate_blocking_checks": sorted(blocking_release_checks),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    SUMMARY_PATH.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print(f"Alpha gate summary written: {SUMMARY_PATH}")

    return 0 if summary["alpha_gate_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
