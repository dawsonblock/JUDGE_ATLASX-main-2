#!/usr/bin/env python3
"""Workspace validation runner for smoke/full profiles with JSON summaries."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = REPO_ROOT / ".validation_logs"

ARTIFACT_SUMMARY = LOG_DIR / "toolathlon_artifact_build_summary.json"
MCP_SMOKE_SUMMARY = LOG_DIR / "toolathlon_mcp_smoke_summary.json"
PREFLIGHT_SUMMARY = LOG_DIR / "toolathlon_preflight_summary.json"
VALIDATION_SUMMARY = LOG_DIR / "validation_summary.json"
DOCKER_PREFLIGHT_SUMMARY = LOG_DIR / "docker_preflight_summary.json"
DOCKER_SMOKE_SUMMARY = LOG_DIR / "docker_mcp_smoke_summary.json"


@dataclass
class Check:
    name: str
    command: list[str]
    timeout_seconds: int | None = None


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_check(check: Check, log_name: str) -> dict:
    log_path = LOG_DIR / log_name
    started_at = now_utc()
    try:
        cp = subprocess.run(
            check.command,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=check.timeout_seconds,
        )
        output = cp.stdout + cp.stderr
        log_path.write_text(output, encoding="utf-8")
        status = "passed" if cp.returncode == 0 else "failed"
        error = None if cp.returncode == 0 else f"exit_code_{cp.returncode}"
        return {
            "name": check.name,
            "status": status,
            "exit_code": cp.returncode,
            "error": error,
            "log_path": str(log_path.relative_to(REPO_ROOT)),
            "started_at": started_at,
            "finished_at": now_utc(),
        }
    except FileNotFoundError:
        log_path.write_text("command not found\n", encoding="utf-8")
        return {
            "name": check.name,
            "status": "failed",
            "exit_code": 127,
            "error": "command_not_found",
            "log_path": str(log_path.relative_to(REPO_ROOT)),
            "started_at": started_at,
            "finished_at": now_utc(),
        }
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or ""
        stderr = exc.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
        output = stdout + stderr
        output += f"\ncommand timed out after {check.timeout_seconds}s\n"
        log_path.write_text(output, encoding="utf-8")
        return {
            "name": check.name,
            "status": "failed",
            "exit_code": 124,
            "error": "timeout",
            "log_path": str(log_path.relative_to(REPO_ROOT)),
            "started_at": started_at,
            "finished_at": now_utc(),
        }


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def command_exists(command: str) -> bool:
    cp = subprocess.run(
        ["bash", "-lc", f"command -v {command}"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return cp.returncode == 0


def preflight_checks(profile: str, run_docker: bool) -> dict:
    required_cmds = ["python3", "node", "npm"]
    if profile == "full":
        required_cmds.append("git")
    if run_docker:
        required_cmds.append("docker")

    found = [cmd for cmd in required_cmds if command_exists(cmd)]
    missing = [cmd for cmd in required_cmds if cmd not in found]

    payload = {
        "profile": profile,
        "status": "passed" if not missing else "failed",
        "required_commands": required_cmds,
        "found": found,
        "missing": missing,
        "found_count": len(found),
        "missing_count": len(missing),
        "generated_at": now_utc(),
    }
    write_json(PREFLIGHT_SUMMARY, payload)
    return payload


def smoke_artifact_checks() -> list[Check]:
    return [
        Check("backend_compile", ["python3", "-m", "compileall", "-q", "backend/app"]),
        Check("validate_workflows", ["python3", "scripts/validate_workflows.py"]),
        Check("check_false_claims", ["python3", "scripts/check_false_claims.py"]),
    ]


def smoke_runtime_checks() -> list[Check]:
    return [
        Check("runtime_smoke", ["python3", "scripts/runtime_smoke.py"]),
        Check("check_dockerfile_copy_paths", ["python3", "scripts/check_dockerfile_copy_paths.py"]),
        Check("check_compose_auth_defaults", ["python3", "scripts/check_compose_auth_defaults.py"]),
        Check(
            "check_frontend_node_gate",
            [
                "bash",
                "-lc",
                (
                    'NVM_DIR="${NVM_DIR:-$HOME/.nvm}"; '
                    '[ -s "$NVM_DIR/nvm.sh" ] && . "$NVM_DIR/nvm.sh"; '
                    "nvm use 22.22.3 >/dev/null 2>&1 || "
                    "{ echo 'BLOCKED_NODE_VERSION: nvm use 22.22.3 failed -- install Node 22.22.3 via: nvm install 22.22.3'; exit 1; }; "
                    "python3 scripts/check_frontend_node_gate.py"
                ),
            ],
        ),
    ]


def full_artifact_checks() -> list[Check]:
    return [
        Check("release_gate", ["python3", "scripts/release_gate.py"], timeout_seconds=600),
        Check("verify_status_consistency", ["python3", "scripts/verify_status_consistency.py"], timeout_seconds=120),
        Check("check_false_claims", ["python3", "scripts/check_false_claims.py"]),
        Check("check_truth_claims", ["python3", "scripts/check_truth_claims.py"], timeout_seconds=120),
        Check("check_source_keys", ["python3", "scripts/check_source_keys.py", "--root", "backend/app", "--repo-root", "."]),
        Check("check_statuses", ["python3", "scripts/check_statuses.py", "--root", "backend/app"]),
        Check("check_yaml_duplicate_keys", ["python3", "scripts/check_yaml_duplicate_keys.py"]),
        Check("validate_workflows", ["python3", "scripts/validate_workflows.py"]),
        Check("check_proof_freshness", ["python3", "scripts/check_proof_freshness.py"], timeout_seconds=120),
        Check("check_external_boundaries", ["python3", "scripts/check_external_boundaries.py"]),
        Check("check_dockerfile_copy_paths", ["python3", "scripts/check_dockerfile_copy_paths.py"]),
        Check("check_compose_auth_defaults", ["python3", "scripts/check_compose_auth_defaults.py"]),
    ]


def summarize_results(profile: str, checks: list[dict], expected_count: int, path: Path) -> dict:
    passed_count = sum(1 for c in checks if c["status"] == "passed")
    failed_count = sum(1 for c in checks if c["status"] != "passed")
    payload = {
        "profile": profile,
        "overall_status": "passed" if failed_count == 0 else "failed",
        "expected_package_count": expected_count,
        "package_count": len(checks),
        "passed_count": passed_count,
        "failed_count": failed_count,
        "checks": checks,
        "generated_at": now_utc(),
    }
    write_json(path, payload)
    return payload


def summarize_runtime(profile: str, checks: list[dict]) -> dict:
    passed_count = sum(1 for c in checks if c["status"] == "passed")
    failed_count = sum(1 for c in checks if c["status"] != "passed")
    payload = {
        "profile": profile,
        "overall_status": "passed" if failed_count == 0 else "failed",
        "target_count": len(checks),
        "passed_count": passed_count,
        "failed_count": failed_count,
        "checks": checks,
        "generated_at": now_utc(),
    }
    write_json(MCP_SMOKE_SUMMARY, payload)
    return payload


def run_docker_checks(profile: str) -> tuple[dict, dict]:
    preflight_result = run_check(
        Check("docker_runtime_preflight", ["bash", "scripts/check_docker_runtime.sh"]),
        "docker_runtime_preflight.log",
    )
    docker_preflight = {
        "profile": profile,
        "status": "passed" if preflight_result["status"] == "passed" else "failed",
        "missing_count": 0 if preflight_result["status"] == "passed" else 1,
        "checks": [preflight_result],
        "generated_at": now_utc(),
    }
    write_json(DOCKER_PREFLIGHT_SUMMARY, docker_preflight)

    if preflight_result["status"] != "passed":
        docker_smoke = {
            "profile": profile,
            "overall_status": "failed",
            "target_count": 1,
            "passed_count": 0,
            "failed_count": 1,
            "checks": [
                {
                    "name": "docker_smoke",
                    "status": "failed",
                    "exit_code": 125,
                    "error": "docker_preflight_failed",
                    "log_path": str((LOG_DIR / "docker_smoke.log").relative_to(REPO_ROOT)),
                    "started_at": now_utc(),
                    "finished_at": now_utc(),
                }
            ],
            "generated_at": now_utc(),
        }
        write_json(DOCKER_SMOKE_SUMMARY, docker_smoke)
        return docker_preflight, docker_smoke

    docker_smoke_result = run_check(
        Check(
            "docker_smoke",
            ["python3", "scripts/docker_smoke.py"],
            timeout_seconds=1800,
        ),
        "docker_smoke_runner.log",
    )
    docker_smoke_result["log_path"] = str(
        (LOG_DIR / "docker_smoke.log").relative_to(REPO_ROOT)
    )
    docker_smoke = {
        "profile": profile,
        "overall_status": "passed" if docker_smoke_result["status"] == "passed" else "failed",
        "target_count": 1,
        "passed_count": 1 if docker_smoke_result["status"] == "passed" else 0,
        "failed_count": 0 if docker_smoke_result["status"] == "passed" else 1,
        "checks": [docker_smoke_result],
        "generated_at": now_utc(),
    }
    write_json(DOCKER_SMOKE_SUMMARY, docker_smoke)
    return docker_preflight, docker_smoke


def write_validation_summary(
    profile: str,
    preflight: dict,
    artifact_summary: dict,
    runtime_summary: dict,
    run_docker: bool,
    docker_preflight: dict | None,
    docker_smoke: dict | None,
) -> dict:
    phase_statuses = {
        "preflight": preflight["status"],
        "artifact_build": artifact_summary["overall_status"],
        "runtime_smoke": runtime_summary["overall_status"],
    }

    if run_docker and docker_preflight and docker_smoke:
        phase_statuses["docker_preflight"] = docker_preflight["status"]
        phase_statuses["docker_smoke"] = docker_smoke["overall_status"]
    else:
        phase_statuses["docker"] = "skipped"

    failed_phase_count = sum(1 for status in phase_statuses.values() if status == "failed")
    overall_status = "passed" if failed_phase_count == 0 else "failed"

    payload = {
        "overall_status": overall_status,
        "failed_phase_count": failed_phase_count,
        "phases": phase_statuses,
        "capabilities": {
            "toolathlon_profile": profile,
            "run_docker": run_docker,
            "python_version": sys.version.split()[0],
            "is_experimental_full": profile == "full",
        },
        "generated_at": now_utc(),
    }
    write_json(VALIDATION_SUMMARY, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=["smoke", "full"], default="smoke")
    parser.add_argument("--run-docker", action="store_true")
    args = parser.parse_args()

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    preflight = preflight_checks(args.profile, args.run_docker)

    artifact_checks = smoke_artifact_checks() if args.profile == "smoke" else full_artifact_checks()
    runtime_checks = smoke_runtime_checks()

    artifact_results = [
        run_check(check, f"artifact_{check.name}.log")
        for check in artifact_checks
    ]
    runtime_results = [
        run_check(check, f"runtime_{check.name}.log")
        for check in runtime_checks
    ]

    for runtime_result in runtime_results:
        if runtime_result.get("name") == "runtime_smoke":
            runtime_result["log_path"] = str(
                (LOG_DIR / "runtime_smoke.log").relative_to(REPO_ROOT)
            )

    expected_count = 3 if args.profile == "smoke" else 12
    artifact_summary = summarize_results(
        args.profile,
        artifact_results,
        expected_count,
        ARTIFACT_SUMMARY,
    )
    runtime_summary = summarize_runtime(args.profile, runtime_results)

    docker_preflight = None
    docker_smoke = None
    if args.run_docker:
        docker_preflight, docker_smoke = run_docker_checks(args.profile)

    validation_summary = write_validation_summary(
        args.profile,
        preflight,
        artifact_summary,
        runtime_summary,
        args.run_docker,
        docker_preflight,
        docker_smoke,
    )

    print(f"validation profile={args.profile} overall_status={validation_summary['overall_status']}")
    print(f"summary: {VALIDATION_SUMMARY}")
    return 0 if validation_summary["overall_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
