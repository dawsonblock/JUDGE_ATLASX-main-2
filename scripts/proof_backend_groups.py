#!/usr/bin/env python3
"""Run backend proof groups with independent logs and a summary artifact."""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
ARTIFACTS_DIR = REPO_ROOT / "artifacts" / "proof"
BACKEND_ARTIFACTS_DIR = ARTIFACTS_DIR / "backend"
SUMMARY_LOG = ARTIFACTS_DIR / "backend_grouped_tests_summary.log"


def _python_exe() -> str:
    venv_python = BACKEND_DIR / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def _run_group(
    name: str,
    command: list[str],
    log_path: Path,
    timeout_seconds: int | None = None,
) -> tuple[str, int, float, bool]:
    t0 = time.monotonic()
    timed_out = False
    with log_path.open("w", encoding="utf-8") as log_file:
        log_file.write(f"GROUP={name}\n")
        log_file.write(f"COMMAND={' '.join(command)}\n\n")
        try:
            proc = subprocess.run(
                command,
                cwd=REPO_ROOT,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
                timeout=timeout_seconds,
            )
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            rc = 124
            log_file.write("\n[proof_backend_groups] TIMEOUT after ")
            log_file.write(f"{timeout_seconds}s\n")
    duration = round(time.monotonic() - t0, 3)
    status = "TIMEOUT" if timed_out else ("PASS" if rc == 0 else "FAIL")
    return status, rc, duration, timed_out


def main() -> int:
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
    BACKEND_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)

    python_exe = _python_exe()
    proof_db_url = f"sqlite:///{(ARTIFACTS_DIR / 'proof_groups.db').resolve()}"
    source_registry_status_path = (
        ARTIFACTS_DIR / "source_registry_status.json"
    ).resolve()

    groups: list[tuple[str, list[str], int | None]] = [
        (
            "backend_compile",
            [
                python_exe,
                "-m",
                "compileall",
                "-q",
                "backend/app",
                "backend/tools",
            ],
            None,
        ),
        (
            "backend_import",
            [python_exe, "backend/scripts/proof_backend_import.py"],
            None,
        ),
        (
            "unit",
            [
                python_exe,
                "-m",
                "pytest",
                "backend/app/tests/test_classifier.py",
                "backend/app/tests/test_source_rules.py",
                "backend/app/tests/test_ingestion_statuses.py",
                "-q",
            ],
            600,
        ),
        (
            "api_contracts",
            [
                python_exe,
                "-m",
                "pytest",
                "backend/app/tests/test_api_contract_public_map.py",
                "backend/app/tests/test_public_api_boundary.py",
                "-q",
            ],
            600,
        ),
        (
            "ingestion_source_gates",
            [
                "bash",
                "-lc",
                (
                    f'JTA_DATABASE_URL="{proof_db_url}" '
                    f"{python_exe} -m pytest "
                    "backend/app/tests/test_ingestion_source_gate.py "
                    "backend/app/tests/test_source_run_policy.py "
                    "backend/app/tests/test_source_automation_status_gate.py "
                    "backend/app/tests/test_source_registry_control_plane.py "
                    "-q"
                ),
            ],
            900,
        ),
        (
            "auth_rbac",
            [
                python_exe,
                "-m",
                "pytest",
                "backend/app/tests/test_auth_session.py",
                "backend/app/tests/test_admin_security.py",
                "backend/app/tests/test_legacy_admin_token_gate.py",
                "backend/app/tests/test_admin_imports_returns_actor.py",
                "backend/app/tests/test_admin_ingest_requires_source_admin.py",
                "-q",
            ],
            900,
        ),
        (
            "public_visibility",
            [
                python_exe,
                "-m",
                "pytest",
                "backend/app/tests/test_public_visibility_gates.py",
                "backend/app/tests/test_public_map_reviewed_only.py",
                "backend/app/tests/test_review_rejected_not_public.py",
                "backend/app/tests/test_evidence_publication_gate.py",
                "-q",
            ],
            900,
        ),
        (
            "evidence_memory",
            [
                python_exe,
                "-m",
                "pytest",
                "backend/app/tests/test_evidence_store.py",
                "backend/app/tests/test_evidence_immutability.py",
                "backend/app/tests/test_memory_public_boundary.py",
                "backend/app/tests/test_memory_claim_lifecycle.py",
                "backend/app/tests/test_memory_checksums.py",
                "-q",
            ],
            900,
        ),
        (
            "justice_laws",
            [
                python_exe,
                "-m",
                "pytest",
                "backend/app/tests/test_justice_laws_xml.py",
                "backend/app/tests/test_justice_laws_phase4.py",
                "-q",
            ],
            900,
        ),
        (
            "source_registry",
            [
                "bash",
                "-lc",
                (
                    f'JTA_DATABASE_URL="{proof_db_url}" '
                    f"{python_exe} -m pytest "
                    "backend/app/tests/test_source_registry_contracts.py "
                    "backend/app/tests/test_source_registry_canada.py "
                    "backend/app/tests/test_source_keys.py -q && "
                    f"{python_exe} scripts/export_source_registry_status.py "
                    "--output "
                    f'"{source_registry_status_path}"'
                ),
            ],
            900,
        ),
        (
            "boundary",
            [python_exe, "backend/scripts/check_repo_boundaries.py"],
            600,
        ),
        (
            "slow_integration",
            [
                python_exe,
                "-m",
                "pytest",
                "backend/app/tests/test_web_monitor_integration.py",
                "backend/app/tests/test_ingestion_runtime.py",
                "-q",
            ],
            1200,
        ),
    ]

    lines: list[str] = ["BACKEND GROUPED TEST SUMMARY", ""]
    any_failures = False
    for name, command, timeout in groups:
        log_path = BACKEND_ARTIFACTS_DIR / f"{name}.log"
        status, rc, duration, _timed_out = _run_group(
            name,
            command,
            log_path,
            timeout,
        )
        relative_log = log_path.relative_to(REPO_ROOT)
        lines.append(
            f"{name}: {status} rc={rc} "
            f"duration_seconds={duration} log={relative_log}"
        )
        if rc != 0:
            any_failures = True

    lines.append("")
    lines.append(f"overall_status={'FAIL' if any_failures else 'PASS'}")
    SUMMARY_LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(f"wrote {SUMMARY_LOG.relative_to(REPO_ROOT)}")
    return 1 if any_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
