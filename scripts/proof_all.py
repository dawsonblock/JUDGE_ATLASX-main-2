#!/usr/bin/env python3
"""Run core proof checks and write canonical proof artifacts.

All step outputs are persisted under ``artifacts/proof/current`` using stable
log filenames so manifest and summary references are reproducible.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import platform
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class StepResult:
    name: str
    command: str
    status: str
    exit_code: int
    duration_seconds: float
    log_path: str


def _run_step(
    repo_root: Path,
    out_dir: Path,
    name: str,
    log_name: str,
    command: list[str],
) -> StepResult:
    log_path = out_dir / log_name
    t0 = datetime.now(timezone.utc)
    with log_path.open("w", encoding="utf-8") as fh:
        proc = subprocess.run(
            command,
            cwd=repo_root,
            stdout=fh,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    duration = (datetime.now(timezone.utc) - t0).total_seconds()
    return StepResult(
        name=name,
        command=" ".join(command),
        status="PASS" if proc.returncode == 0 else "FAIL",
        exit_code=proc.returncode,
        duration_seconds=round(duration, 3),
        log_path=str(log_path.relative_to(repo_root)),
    )


def _logs_exist(repo_root: Path, results: list[StepResult]) -> tuple[bool, list[str]]:
    missing: list[str] = []
    for result in results:
        if not (repo_root / result.log_path).exists():
            missing.append(result.log_path)
    return len(missing) == 0, missing


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    out_dir = repo_root / "artifacts" / "proof" / "current"
    out_dir.mkdir(parents=True, exist_ok=True)
    proof_db_url = f"sqlite:///{(out_dir / 'proof.db').resolve()}"

    backend_venv_python = repo_root / "backend" / ".venv" / "bin" / "python"
    python_exe = str(backend_venv_python) if backend_venv_python.exists() else sys.executable
    steps: list[tuple[str, str, list[str]]] = [
        ("check_no_pyc", "check_no_pyc.log", ["bash", "scripts/check_no_pyc.sh"]),
        ("check_false_claims", "check_false_claims.log", [python_exe, "scripts/check_false_claims.py"]),
        (
            "check_external_boundaries",
            "check_external_boundaries.log",
            [python_exe, "scripts/check_external_boundaries.py"],
        ),
        (
            "prepare_proof_db",
            "prepare_proof_db.log",
            [python_exe, "scripts/prepare_proof_db.py", "--proof-db", str(out_dir / "proof.db")],
        ),
        ("validate_sources", "validate_sources.log", [python_exe, "backend/tools/validate_sources.py"]),
        (
            "verify_evidence_store",
            "verify_evidence_store.log",
            ["bash", "-lc", f'JTA_DATABASE_URL="{proof_db_url}" {python_exe} backend/tools/verify_evidence_store.py'],
        ),
        (
            "verify_audit_chain",
            "verify_audit_chain.log",
            ["bash", "-lc", f'JTA_DATABASE_URL="{proof_db_url}" {python_exe} backend/tools/verify_audit_chain.py'],
        ),
        (
            "auth_mutation_route_coverage",
            "auth_mutation_route_coverage.log",
            [python_exe, "-m", "pytest", "backend/app/tests/test_mutation_route_authority_coverage.py", "-q"],
        ),
        (
            "check_api_contracts",
            "check_api_contracts.log",
            [python_exe, "scripts/check_api_contracts.py"],
        ),
        (
            "check_migrations",
            "check_migrations.log",
            [python_exe, "backend/tools/check_migrations.py"],
        ),
        (
            "check_npm_audit_triage",
            "check_npm_audit_triage.log",
            [python_exe, "scripts/check_npm_audit_triage.py"],
        ),
        (
            "map_route_check",
            "map_route_check.log",
            [python_exe, "scripts/check_map_route.py"],
        ),
        (
            "public_api_boundary",
            "public_api_boundary.log",
            [python_exe, "-m", "pytest", "backend/app/tests", "-k", "public_api", "-q"],
        ),
        (
            "backend_compile",
            "backend_compile.log",
            [python_exe, "-m", "compileall", "-q", "backend/app", "backend/tools"],
        ),
        (
            "backend_pytest",
            "backend_pytest.log",
            [
                "bash",
                "-lc",
                f'JTA_DATABASE_URL="{proof_db_url}" uv run --directory "{repo_root / "backend"}" pytest app/tests -q',
            ],
        ),
        (
            "frontend_install",
            "frontend_install.log",
            ["npm", "ci", "--prefix", str(repo_root / "frontend")],
        ),
        (
            "frontend_lint",
            "frontend_lint.log",
            ["npm", "run", "lint", "--prefix", str(repo_root / "frontend")],
        ),
        (
            "frontend_typecheck",
            "frontend_typecheck.log",
            ["npm", "run", "typecheck", "--prefix", str(repo_root / "frontend")],
        ),
        (
            "frontend_contracts",
            "frontend_contracts.log",
            ["npm", "run", "test:contracts", "--prefix", str(repo_root / "frontend")],
        ),
        (
            "frontend_build",
            "frontend_build.log",
            ["npm", "run", "build", "--prefix", str(repo_root / "frontend")],
        ),
    ]

    results: list[StepResult] = []
    for step_name, log_name, command in steps:
        results.append(_run_step(repo_root, out_dir, step_name, log_name, command))

    logs_ok, missing_logs = _logs_exist(repo_root, results)

    summary_path = out_dir / "proof_all_summary.json"
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "repo_root": str(repo_root),
        "steps": [asdict(r) for r in results],
        "ok": all(r.exit_code == 0 for r in results) and logs_ok,
        "missing_logs": missing_logs,
    }
    summary_path.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )

    manifest_path = out_dir / "manifest.json"
    manifest_payload = {
        "generated_at": payload["generated_at"],
        "git_commit": os.environ.get("GIT_COMMIT", "unknown"),
        "repo_name": "JUDGE_ATLAS",
        "python_version": sys.version.split()[0],
        "node_version": subprocess.run(["node", "--version"], capture_output=True, text=True).stdout.strip() or "unknown",
        "npm_version": subprocess.run(["npm", "--version"], capture_output=True, text=True).stdout.strip() or "unknown",
        "platform": platform.platform(),
        "backend_test_command": "uv run --directory backend pytest -q",
        "frontend_build_command": "npm run build --prefix frontend",
        "migration_command": "python backend/tools/check_migrations.py",
        "source_validation_command": "python backend/tools/validate_sources.py",
        "evidence_verification_command": "python backend/tools/verify_evidence_store.py",
        "audit_verification_command": "python backend/tools/verify_audit_chain.py",
        "contract_validation_command": "python scripts/check_api_contracts.py",
        "release_gate_command": "python scripts/release_gate.py",
        "result": "pass" if payload["ok"] else "fail",
        "logs": [r.log_path for r in results],
        "known_failures": [],
        "known_limitations": ["alpha gate only; not a production release gate"],
    }
    manifest_path.write_text(json.dumps(manifest_payload, indent=2) + "\n", encoding="utf-8")

    env_path = out_dir / "environment_info.txt"
    env_lines = [
        f"OS={platform.platform()}",
        f"Python={sys.version.split()[0]}",
        f"pip={subprocess.run([sys.executable, '-m', 'pip', '--version'], capture_output=True, text=True).stdout.strip()}",
        f"Node={manifest_payload['node_version']}",
        f"npm={manifest_payload['npm_version']}",
        f"WorkingDirectory={repo_root}",
        f"JTA_APP_ENV={os.environ.get('JTA_APP_ENV', 'unset')}",
        f"JTA_DATABASE_URL={os.environ.get('JTA_DATABASE_URL', 'unset')}",
        f"JTA_JWT_AUTH_ENABLED={os.environ.get('JTA_JWT_AUTH_ENABLED', 'unset')}",
        f"JTA_ENABLE_LEGACY_ADMIN_TOKEN={os.environ.get('JTA_ENABLE_LEGACY_ADMIN_TOKEN', 'unset')}",
        f"JTA_ENFORCE_JWT_MUTATIONS={os.environ.get('JTA_ENFORCE_JWT_MUTATIONS', 'unset')}",
    ]
    env_path.write_text("\n".join(env_lines) + "\n", encoding="utf-8")

    if payload["ok"]:
        print(f"PASS: wrote {summary_path.relative_to(repo_root)}")
        return 0

    print(f"FAIL: wrote {summary_path.relative_to(repo_root)}")
    for r in results:
        if r.exit_code != 0:
            print(f"- {r.name} rc={r.exit_code} log={r.log_path}")
    for missing in missing_logs:
        print(f"- missing_log={missing}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
