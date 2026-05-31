#!/usr/bin/env python3
"""Runtime smoke checks for backend startup/import readiness.

Writes a canonical summary log to .validation_logs/runtime_smoke.log.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPO_ROOT / "backend"
LOG_DIR = REPO_ROOT / ".validation_logs"
LOG_PATH = LOG_DIR / "runtime_smoke.log"


def _write(lines: list[str]) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    LOG_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _backend_python() -> str:
    venv_python = BACKEND_ROOT / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def _run(cmd: list[str], *, cwd: Path, timeout: int = 60) -> tuple[int, str]:
    cp = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout,
    )
    output = (cp.stdout or "") + (cp.stderr or "")
    return cp.returncode, output


def main() -> int:
    lines: list[str] = [
        "runtime smoke",
        f"repo_root: {REPO_ROOT}",
        f"backend_root: {BACKEND_ROOT}",
    ]

    failed = False
    python_exe = _backend_python()
    lines.append(f"python_executable: {python_exe}")

    # 1) Dependency imports
    rc, output = _run(
        [
            python_exe,
            "-c",
            (
                "import fastapi, sqlalchemy, pydantic_settings, alembic; "
                "print('imports_ok')"
            ),
        ],
        cwd=BACKEND_ROOT,
    )
    if rc == 0:
        lines.append("dependency import: PASS")
    else:
        failed = True
        lines.append("dependency import: FAIL")
        lines.append(output.strip() or "no output")

    # 2) Settings load + DB URL presence
    rc, output = _run(
        [
            python_exe,
            "-c",
            (
                "from app.core.config import get_settings; "
                "s=get_settings(); "
                "assert bool(getattr(s, 'database_url', '')); "
                "print('settings_ok')"
            ),
        ],
        cwd=BACKEND_ROOT,
    )
    if rc == 0:
        lines.append("settings load: PASS")
        lines.append("database url exists: PASS")
    else:
        failed = True
        lines.append("settings load: FAIL")
        lines.append(output.strip() or "no output")

    # 3) FastAPI app import
    rc, output = _run(
        [
            python_exe,
            "-c",
            (
                "from fastapi import FastAPI; "
                "from app.main import app; "
                "assert isinstance(app, FastAPI); "
                "print('app_import_ok')"
            ),
        ],
        cwd=BACKEND_ROOT,
    )
    if rc == 0:
        lines.append("fastapi app import: PASS")
    else:
        failed = True
        lines.append("fastapi app import: FAIL")
        lines.append(output.strip() or "no output")

    # 4) Route registry checks
    rc, output = _run(
        [
            python_exe,
            "-c",
            (
                "from app.main import app; "
                "paths={getattr(r, 'path', '') for r in app.routes}; "
                "assert len(paths) > 0; "
                "assert '/health' in paths; "
                "print(f'routes={len(paths)}')"
            ),
        ],
        cwd=BACKEND_ROOT,
    )
    if rc == 0:
        lines.append("route mount check: PASS")
    else:
        failed = True
        lines.append("route mount check: FAIL")
        lines.append(output.strip() or "no output")

    # 5) Alembic config/head
    alembic_ini = BACKEND_ROOT / "alembic.ini"
    if not alembic_ini.exists():
        failed = True
        lines.append("alembic config check: FAIL")
        lines.append(f"missing file: {alembic_ini}")
    else:
        rc, output = _run(
            [python_exe, "-m", "alembic", "-c", "alembic.ini", "heads"],
            cwd=BACKEND_ROOT,
            timeout=120,
        )
        if rc == 0:
            lines.append("alembic config check: PASS")
        else:
            failed = True
            lines.append("alembic config check: FAIL")
            lines.append(output.strip() or "no output")

    lines.append("runtime smoke: PASS" if not failed else "runtime smoke: FAIL")
    _write(lines)
    print("\n".join(lines))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
