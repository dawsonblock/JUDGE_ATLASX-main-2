#!/usr/bin/env python3
# trunk-ignore-all(ALL)
"""Docker smoke checks for local release gating.

Writes canonical output to .validation_logs/docker_smoke.log.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
LOG_DIR = REPO_ROOT / ".validation_logs"
LOG_PATH = LOG_DIR / "docker_smoke.log"
REUSABLE_IMAGE_TAGS = (
    "judge_atlas-main2-backend:latest",
    "judge_atlas-main2-frontend:latest",
)


def _compose_command() -> list[str]:
    if subprocess.run(
        ["docker", "compose", "version"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=_docker_timeout(20),
    ).returncode == 0:
        return ["docker", "compose"]

    raise SmokeError("docker_compose_plugin_missing")


def _docker_timeout(default: int) -> int:
    try:
        gate_timeout = int(os.environ.get("JTA_DOCKER_CHECK_TIMEOUT", "180"))
    except ValueError:
        gate_timeout = 180
    return max(default, gate_timeout, 60)


class SmokeError(RuntimeError):
    pass


def _log(lines: list[str]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _append(lines: list[str], message: str) -> None:
    lines.append(message)
    _log(lines)


def _run(
    lines: list[str],
    cmd: list[str],
    *,
    timeout: int,
    allow_failure: bool = False,
) -> subprocess.CompletedProcess[str]:
    _append(lines, f"$ {' '.join(cmd)}")
    cp = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    output = ((cp.stdout or "") + (cp.stderr or "")).strip()
    if output:
        _append(lines, output)
    if cp.returncode != 0 and not allow_failure:
        raise SmokeError(f"command_failed:{' '.join(cmd)}:rc={cp.returncode}")
    return cp


def _append_logs(lines: list[str], service: str) -> None:
    try:
        compose_cmd = _compose_command()
        cp = subprocess.run(
            [*compose_cmd, "logs", service, "--tail", "200"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=_docker_timeout(30),
        )
    except Exception as exc:  # pragma: no cover - defensive logging path
        _append(lines, f"log_capture_error:{service}:{exc}")
        return
    _append(lines, f"--- {service} logs (tail 200) ---")
    if cp.stdout:
        _append(lines, cp.stdout.rstrip())
    if cp.stderr:
        _append(lines, cp.stderr.rstrip())


def _wait_http(
    lines: list[str],
    url: str,
    attempts: int,
    timeout: int,
) -> bool:
    for attempt in range(1, attempts + 1):
        cp = subprocess.run(
            ["curl", "-fsS", url],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
        if cp.returncode == 0:
            _append(lines, f"http_ready:{url}:attempt={attempt}")
            return True
        time.sleep(2)
    return False


def _reuse_existing_images_requested() -> bool:
    return os.environ.get(
        "JTA_DOCKER_SMOKE_REUSE_EXISTING_IMAGES",
        "",
    ).lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _reusable_images_present() -> bool:
    cp = subprocess.run(
        ["docker", "image", "inspect", *REUSABLE_IMAGE_TAGS],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=_docker_timeout(30),
    )
    return cp.returncode == 0


def main() -> int:
    lines: list[str] = ["docker smoke", f"repo_root: {REPO_ROOT}"]
    _log(lines)
    failed = False
    compose_cmd = _compose_command()

    try:
        _run(
            lines,
            [*compose_cmd, "down", "-v"],
            timeout=_docker_timeout(20),
            allow_failure=True,
        )

        if _reuse_existing_images_requested() and _reusable_images_present():
            _append(
                lines,
                (
                    "docker compose build: SKIP "
                    "(reusing existing backend/frontend images)"
                ),
            )
        else:
            _run(lines, [*compose_cmd, "build"], timeout=300)
            _append(lines, "docker compose build: PASS")

        _run(
            lines,
            [*compose_cmd, "up", "-d", "db", "redis", "minio"],
            timeout=300,
        )

        # Postgres (db service)
        postgres_ok = False
        for attempt in range(1, 31):
            cp = _run(
                lines,
                [
                    *compose_cmd,
                    "exec",
                    "-T",
                    "db",
                    "pg_isready",
                    "-U",
                    "judgetracker",
                    "-d",
                    "judgetracker",
                ],
                timeout=10,
                allow_failure=True,
            )
            if cp.returncode == 0:
                postgres_ok = True
                break
            time.sleep(2)
        if not postgres_ok:
            raise SmokeError("postgres_not_healthy")
        _append(lines, "postgres health: PASS")

        # Redis
        redis_ok = False
        for _ in range(20):
            cp = _run(
                lines,
                [*compose_cmd, "exec", "-T", "redis", "redis-cli", "ping"],
                timeout=_docker_timeout(20),
                allow_failure=True,
            )
            if "PONG" in ((cp.stdout or "") + (cp.stderr or "")):
                redis_ok = True
                break
        if not redis_ok:
            raise SmokeError("redis_not_healthy")
        _append(lines, "redis health: PASS")

        # MinIO
        if not _wait_http(
            lines,
            "http://localhost:9000/minio/health/live",
            attempts=30,
            timeout=5,
        ):
            raise SmokeError("minio_not_healthy")
        _append(lines, "minio health: PASS")

        _run(lines, [*compose_cmd, "up", "-d", "backend"], timeout=300)

        backend_ready = _wait_http(
            lines,
            "http://localhost:8000/health",
            attempts=40,
            timeout=5,
        )
        if not backend_ready:
            backend_ready = _wait_http(
                lines,
                "http://localhost:8000/api/health",
                attempts=10,
                timeout=5,
            )
        if not backend_ready:
            raise SmokeError("backend_health_endpoint_failed")
        _append(lines, "backend health: PASS")

        # Verify migrations are healthy in container
        cp = _run(
            lines,
            [*compose_cmd, "exec", "-T", "backend", "alembic", "heads"],
            timeout=60,
            allow_failure=True,
        )
        heads_output = ((cp.stdout or "") + (cp.stderr or "")).lower()
        if cp.returncode != 0:
            raise SmokeError("backend_alembic_heads_failed")
        if "head" not in heads_output:
            raise SmokeError("backend_alembic_heads_missing")

        _run(lines, [*compose_cmd, "up", "-d", "frontend"], timeout=300)
        if not _wait_http(
            lines,
            "http://localhost:3000",
            attempts=40,
            timeout=5,
        ):
            raise SmokeError("frontend_http_failed")

        # Frontend -> backend reachability from container using node runtime.
        cp = _run(
            lines,
            [
                *compose_cmd,
                "exec",
                "-T",
                "frontend",
                "node",
                "-e",
                (
                    "const http=require('http');"
                    "http.get('http://backend:8000/health',res=>{"
                    "if(res.statusCode>=200&&res.statusCode<400){"
                    "process.exit(0);}"
                    "process.exit(1);"
                    "}).on('error',()=>process.exit(1));"
                ),
            ],
            timeout=_docker_timeout(30),
            allow_failure=True,
        )
        if cp.returncode != 0:
            raise SmokeError("frontend_cannot_reach_backend")
        _append(lines, "frontend health: PASS")

        _append(lines, "docker smoke: PASS")
        _run(
            lines,
            [*compose_cmd, "down", "-v"],
            timeout=_docker_timeout(20),
            allow_failure=True,
        )
        _log(lines)
        return 0

    except SmokeError as exc:
        failed = True
        _append(lines, f"docker smoke failure: {exc}")
        for service in ("db", "redis", "minio", "backend", "frontend"):
            _append_logs(lines, service)
    except subprocess.TimeoutExpired as exc:
        failed = True
        _append(lines, f"docker smoke timeout: {exc}")
        for service in ("db", "redis", "minio", "backend", "frontend"):
            _append_logs(lines, service)
    finally:
        try:
            _run(
                lines,
                [*compose_cmd, "down", "-v"],
                timeout=_docker_timeout(20),
                allow_failure=True,
            )
        except Exception:
            _append(lines, "docker compose down -v failed during cleanup")
        _append(
            lines,
            "docker smoke: FAIL" if failed else "docker smoke: PASS",
        )
        _log(lines)
        print("\n".join(lines))

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
