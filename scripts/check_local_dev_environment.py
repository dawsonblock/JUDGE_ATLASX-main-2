#!/usr/bin/env python3
"""Check local alpha developer environment and print machine-readable status."""

from __future__ import annotations

import json
import os
import platform
import shutil
import socket
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class CheckResult:
    name: str
    status: str  # PASS | WARN | FAIL
    detail: str


def _run_cmd(cmd: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, str(exc)
    output = (proc.stdout or proc.stderr or "").strip()
    return proc.returncode, output


def _parse_semver(text: str) -> tuple[int, int, int] | None:
    value = text.strip().lstrip("v")
    parts = value.split(".")
    if len(parts) < 2:
        return None
    try:
        major = int(parts[0])
        minor = int(parts[1])
        patch = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        return None
    return major, minor, patch


def _load_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip().strip('"').strip("'")
    return data


def _socket_open(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.5):
            return True
    except OSError:
        return False


def check_environment(root: Path) -> tuple[list[CheckResult], bool]:
    results: list[CheckResult] = []

    # Python 3.11.x
    py_ok = sys.version_info.major == 3 and sys.version_info.minor == 11
    results.append(
        CheckResult(
            name="python_version",
            status="PASS" if py_ok else "FAIL",
            detail=f"Python {platform.python_version()} detected; requires 3.11.x",
        )
    )

    # Node 22.x
    node_rc, node_output = _run_cmd(["node", "--version"])
    node_ver = _parse_semver(node_output) if node_rc == 0 else None
    node_ok = bool(node_ver and node_ver[0] == 22)
    results.append(
        CheckResult(
            name="node_version",
            status="PASS" if node_ok else "FAIL",
            detail=(
                f"Node {node_output} detected; requires 22.x"
                if node_rc == 0
                else "Node unavailable"
            ),
        )
    )

    # npm 10.x
    npm_rc, npm_output = _run_cmd(["npm", "--version"])
    npm_ver = _parse_semver(npm_output) if npm_rc == 0 else None
    npm_ok = bool(npm_ver and npm_ver[0] == 10)
    results.append(
        CheckResult(
            name="npm_version",
            status="PASS" if npm_ok else "FAIL",
            detail=(
                f"npm {npm_output} detected; requires 10.x"
                if npm_rc == 0
                else "npm unavailable"
            ),
        )
    )

    env_path = root / ".env"
    env_data = _load_env_file(env_path)
    env_present = env_path.exists()
    results.append(
        CheckResult(
            name="env_file",
            status="PASS" if env_present else "FAIL",
            detail=".env exists" if env_present else "Missing .env (copy from .env.example)",
        )
    )

    # Docker availability
    docker_bin = shutil.which("docker")
    if not docker_bin:
        results.append(
            CheckResult(
                name="docker",
                status="FAIL",
                detail="docker CLI not found",
            )
        )
    else:
        docker_rc, docker_output = _run_cmd(["docker", "info", "--format", "{{.ServerVersion}}"])
        if docker_rc == 0:
            results.append(
                CheckResult(
                    name="docker",
                    status="PASS",
                    detail=f"Docker daemon reachable ({docker_output})",
                )
            )
        else:
            results.append(
                CheckResult(
                    name="docker",
                    status="FAIL",
                    detail="docker CLI found but daemon unavailable",
                )
            )

    # Postgres/PostGIS availability or fallback
    db_url = env_data.get("JTA_DATABASE_URL", "")
    if "postgresql" in db_url.lower() and _socket_open("localhost", 5432):
        results.append(
            CheckResult(
                name="postgres",
                status="PASS",
                detail="PostgreSQL reachable on localhost:5432",
            )
        )
    elif "sqlite" in db_url.lower() or not db_url:
        results.append(
            CheckResult(
                name="postgres",
                status="WARN",
                detail="PostgreSQL unavailable; SQLite/local fallback mode",
            )
        )
    else:
        results.append(
            CheckResult(
                name="postgres",
                status="WARN",
                detail="JTA_DATABASE_URL points to PostgreSQL but localhost:5432 unavailable",
            )
        )

    # Redis availability or fallback
    redis_url = env_data.get("JTA_REDIS_URL", "")
    if redis_url and _socket_open("localhost", 6379):
        results.append(
            CheckResult(
                name="redis",
                status="PASS",
                detail="Redis reachable on localhost:6379",
            )
        )
    else:
        results.append(
            CheckResult(
                name="redis",
                status="WARN",
                detail="Redis unavailable; local queue/rate-limit fallback only",
            )
        )

    # Frontend dependencies installed
    frontend_node_modules = root / "frontend" / "node_modules"
    frontend_ok = frontend_node_modules.exists()
    results.append(
        CheckResult(
            name="frontend_dependencies",
            status="PASS" if frontend_ok else "FAIL",
            detail=(
                "frontend/node_modules present"
                if frontend_ok
                else "Missing frontend dependencies (run scripts/bootstrap_frontend.sh)"
            ),
        )
    )

    # Backend dependencies installed
    backend_venv_python = root / "backend" / ".venv" / "bin" / "python"
    if backend_venv_python.exists():
        backend_rc, _ = _run_cmd([str(backend_venv_python), "-c", "import fastapi; print('ok')"])
        backend_ok = backend_rc == 0
    else:
        backend_ok = False
    results.append(
        CheckResult(
            name="backend_dependencies",
            status="PASS" if backend_ok else "FAIL",
            detail=(
                "backend/.venv is ready"
                if backend_ok
                else "Missing backend dependencies (run scripts/bootstrap_backend.sh)"
            ),
        )
    )

    evidence_root = env_data.get("JTA_EVIDENCE_STORE_ROOT", "")
    evidence_required = env_data.get("JTA_EVIDENCE_STORE_REQUIRED", "false").lower() == "true"
    evidence_exists = bool(evidence_root and Path(evidence_root).expanduser().exists())

    if evidence_exists:
        results.append(
            CheckResult(
                name="evidence_store_root",
                status="PASS",
                detail=f"Evidence store root exists: {evidence_root}",
            )
        )
    elif evidence_required:
        results.append(
            CheckResult(
                name="evidence_store_root",
                status="FAIL",
                detail="JTA_EVIDENCE_STORE_REQUIRED=true but JTA_EVIDENCE_STORE_ROOT missing/unavailable",
            )
        )
    else:
        results.append(
            CheckResult(
                name="evidence_store_root",
                status="WARN",
                detail="Evidence store root not configured (acceptable for local development)",
            )
        )

    has_failures = any(r.status == "FAIL" for r in results)
    return results, has_failures


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    results, has_failures = check_environment(root)

    for r in results:
        print(f"{r.status}: {r.detail}")

    report = {
        "ok": not has_failures,
        "summary": {
            "pass": sum(1 for r in results if r.status == "PASS"),
            "warn": sum(1 for r in results if r.status == "WARN"),
            "fail": sum(1 for r in results if r.status == "FAIL"),
        },
        "checks": [asdict(r) for r in results],
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 1 if has_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
