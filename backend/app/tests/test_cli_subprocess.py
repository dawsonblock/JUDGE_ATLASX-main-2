"""Subprocess CLI tests for judgectl.

These tests run the actual installed ``judgectl`` command through
``subprocess``, proving that an AI agent can safely call the CLI from a shell.

A dedicated SQLite database is created and seeded at module import time so
that the subprocess invocations find a populated source_registry table.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# ── helpers ───────────────────────────────────────────────────────────────────

_SUBPROCESS_DB = Path(__file__).with_name("subprocess_test.db")


def _ensure_seeded_db() -> None:
    """Create and seed the subprocess test database if it does not exist."""
    if _SUBPROCESS_DB.exists():
        _SUBPROCESS_DB.unlink()
    env = {
        **os.environ,
        "JTA_APP_ENV": "development",
        "JTA_ADMIN_TOKEN": "test-token",
        "JTA_DATABASE_URL": f"sqlite:///{_SUBPROCESS_DB}",
        "JTA_AUTO_SEED": "true",
        "JTA_RATE_LIMIT_ENABLED": "false",
        "JTA_ENABLE_ADMIN_REVIEW": "true",
        "JTA_ADMIN_REVIEW_TOKEN": "test-token",
    }
    # Import inside subprocess env to create tables and seed registry.
    seed_script = Path(__file__).parent / "_seed_subprocess_db.py"
    if not seed_script.exists():
        seed_script.write_text(
            "import os, sys\n"
            "sys.path.insert(0, str(__import__('pathlib').Path(__file__).parents[3]))\n"
            "from app.db.session import Base, SessionLocal, engine\n"
            "from app.models.entities import *  # noqa\n"
            "from app.seed.source_registry import seed_source_registry\n"
            "Base.metadata.create_all(bind=engine)\n"
            "with SessionLocal() as db:\n"
            "    seed_source_registry(db)\n"
            "    db.commit()\n"
            "print('seeded')\n"
        )
    result = subprocess.run(
        [sys.executable, str(seed_script)],
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to seed subprocess test DB:\n{result.stderr}"
        )


# Seed once at module load time (before any test runs).
_ensure_seeded_db()

# Build an environment that points the subprocess at the seeded database.
_ENV = {
    **os.environ,
    "JTA_APP_ENV": "development",
    "JTA_ADMIN_TOKEN": "test-token",
    "JTA_DATABASE_URL": f"sqlite:///{_SUBPROCESS_DB}",
    "JTA_AUTO_SEED": "true",
    "JTA_RATE_LIMIT_ENABLED": "false",
    "JTA_ENABLE_ADMIN_REVIEW": "true",
    "JTA_ADMIN_REVIEW_TOKEN": "test-token",
}


def _run(*args: str) -> subprocess.CompletedProcess[str]:
    """Run judgectl with *args* and return the completed process."""
    venv_cli = Path(sys.executable).parent / "judgectl"
    cli_cmd = str(venv_cli) if venv_cli.exists() else (shutil.which("judgectl") or "judgectl")
    return subprocess.run(
        [cli_cmd, *args],
        capture_output=True,
        text=True,
        env=_ENV,
    )


def _run_json(*args: str) -> tuple[subprocess.CompletedProcess[str], dict]:
    """Run judgectl --json with *args* and parse the JSON output."""
    proc = _run("--json", *args)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        pytest.fail(
            f"judgectl --json {' '.join(args)} produced non-JSON output:\n"
            f"stdout: {proc.stdout!r}\nstderr: {proc.stderr!r}\n{exc}"
        )
    return proc, data


# ── basic availability ────────────────────────────────────────────────────────


def test_subprocess_help_exits_zero() -> None:
    """judgectl --help must exit 0 and mention 'judgectl'."""
    proc = _run("--help")
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    assert "judgectl" in proc.stdout.lower() or "usage" in proc.stdout.lower()


# ── health ────────────────────────────────────────────────────────────────────


def test_subprocess_health_json() -> None:
    """judgectl --json health must return a valid JSON envelope with ok=true."""
    proc, data = _run_json("health")
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    assert data["ok"] is True
    assert data["command"] == "health"
    assert "source_registry_count" in data["data"]
    assert isinstance(data["data"]["source_registry_count"], int)


# ── sources list ──────────────────────────────────────────────────────────────


def test_subprocess_sources_list_json() -> None:
    """judgectl --json sources list must return a list of sources."""
    proc, data = _run_json("sources", "list")
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    assert data["ok"] is True
    assert data["command"] == "sources.list"
    assert isinstance(data["data"], list)
    assert len(data["data"]) > 0
    first = data["data"][0]
    assert "source_key" in first
    assert "source_class" in first
    assert "is_active" in first


# ── sources validate ──────────────────────────────────────────────────────────


def test_subprocess_sources_validate_json() -> None:
    """judgectl --json sources validate must return a stable JSON envelope."""
    proc, data = _run_json("sources", "validate")
    # May succeed or fail depending on script state; envelope must be valid JSON.
    assert isinstance(data.get("ok"), bool)
    assert data["command"] == "sources.validate"


# ── audit guards ─────────────────────────────────────────────────────────────


def test_subprocess_audit_guards_shape() -> None:
    """judgectl --json audit guards must return a valid JSON envelope with checks list."""
    proc, data = _run_json("audit", "guards")
    # Shape test: always verify the envelope structure.
    assert isinstance(data.get("ok"), bool)
    assert data["command"] == "audit.guards"
    assert "data" in data
    assert isinstance(data["data"].get("checks"), list)
    for check in data["data"]["checks"]:
        assert "name" in check
        assert "ok" in check


def test_subprocess_audit_guards_all_pass() -> None:
    """judgectl --json audit guards must exit 0 and report ok=true with all checks passing.

    This is the proof-mode test.  All CI guards must pass in a clean environment.
    """
    proc, data = _run_json("audit", "guards")
    assert proc.returncode == 0, (
        f"audit guards exited non-zero.\n"
        f"stdout: {proc.stdout[:500]}\nstderr: {proc.stderr[:200]}"
    )
    assert data["ok"] is True, (
        f"audit guards returned ok=false.\n"
        f"Failing checks: {[c for c in data.get('data', {}).get('checks', []) if not c.get('ok')]}"
    )
    assert data["data"]["all_passed"] is True, (
        f"audit guards all_passed=false.\n"
        f"Errors: {data.get('data', {}).get('errors', [])}"
    )


# ── blocked ingestion ─────────────────────────────────────────────────────────


def test_subprocess_ingest_portal_reference_blocked() -> None:
    """Ingesting a portal_reference source must exit non-zero with SOURCE_NOT_RUNNABLE."""
    proc, data = _run_json("ingest", "run", "saskatoon_open_data_crime")
    assert proc.returncode != 0, "Expected non-zero exit for portal_reference source"
    assert data["ok"] is False
    assert data["error_code"] == "SOURCE_NOT_RUNNABLE"
    assert data["source_key"] == "saskatoon_open_data_crime"
    assert data["source_class"] == "portal_reference"


def test_subprocess_ingest_disabled_stub_blocked() -> None:
    """Ingesting a disabled_stub source must exit non-zero with SOURCE_NOT_RUNNABLE."""
    proc, data = _run_json("ingest", "run", "canada_justice_laws")
    assert proc.returncode != 0, "Expected non-zero exit for disabled_stub source"
    assert data["ok"] is False
    assert data["error_code"] == "SOURCE_NOT_RUNNABLE"


def test_subprocess_ingest_nonexistent_blocked() -> None:
    """Ingesting a non-existent source must exit non-zero with SOURCE_NOT_FOUND."""
    proc, data = _run_json("ingest", "run", "totally_fake_source_xyz")
    assert proc.returncode != 0
    assert data["ok"] is False
    assert data["error_code"] == "SOURCE_NOT_FOUND"


# ── sources enable policy ─────────────────────────────────────────────────────


def test_subprocess_enable_portal_reference_blocked() -> None:
    """Enabling a portal_reference source must exit non-zero with SOURCE_NOT_RUNNABLE."""
    proc, data = _run_json("sources", "enable", "saskatoon_police_open_data", "--yes")
    assert proc.returncode != 0
    assert data["ok"] is False
    assert data["error_code"] == "SOURCE_NOT_RUNNABLE"
    assert data["source_class"] == "portal_reference"


# ── JSON envelope contract ────────────────────────────────────────────────────


def test_subprocess_json_success_envelope_shape() -> None:
    """Successful JSON output must have ok, command, data, warnings, errors."""
    _, data = _run_json("health")
    assert set(data.keys()) >= {"ok", "command", "data", "warnings", "errors"}
    assert isinstance(data["warnings"], list)
    assert isinstance(data["errors"], list)


def test_subprocess_json_error_envelope_shape() -> None:
    """Error JSON output must have ok, command, error_code, message, next_action."""
    _, data = _run_json("ingest", "run", "saskatoon_police_open_data")
    assert set(data.keys()) >= {"ok", "command", "error_code", "message", "next_action"}
    assert data["ok"] is False
