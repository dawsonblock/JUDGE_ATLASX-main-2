"""CliRunner tests for judgectl commands.

These tests use Click's CliRunner to invoke commands in-process.
The test database is configured by conftest.py before any imports.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from app.cli.main import main


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture(scope="session", autouse=True)
def seed_registry() -> None:
    """Populate SourceRegistry from YAML before any CLI test runs."""
    from app.db.session import SessionLocal
    from app.seed.source_registry import seed_source_registry

    with SessionLocal() as db:
        seed_source_registry(db)
        db.commit()


# ── help ─────────────────────────────────────────────────────────────────────


def test_help(runner: CliRunner) -> None:
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "judgectl" in result.output.lower() or "usage" in result.output.lower()


def test_sources_help(runner: CliRunner) -> None:
    result = runner.invoke(main, ["sources", "--help"])
    assert result.exit_code == 0


def test_ingest_help(runner: CliRunner) -> None:
    result = runner.invoke(main, ["ingest", "--help"])
    assert result.exit_code == 0


def test_audit_help(runner: CliRunner) -> None:
    result = runner.invoke(main, ["audit", "--help"])
    assert result.exit_code == 0


# ── health ────────────────────────────────────────────────────────────────────


def test_health_json(runner: CliRunner) -> None:
    result = runner.invoke(main, ["--json", "health"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["ok"] is True
    assert data["command"] == "health"
    assert "source_registry_count" in data["data"]
    assert isinstance(data["data"]["source_registry_count"], int)


def test_health_human(runner: CliRunner) -> None:
    result = runner.invoke(main, ["health"])
    assert result.exit_code == 0
    assert "status" in result.output


# ── sources list ──────────────────────────────────────────────────────────────


def test_sources_list_json(runner: CliRunner) -> None:
    result = runner.invoke(main, ["--json", "sources", "list"])
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["ok"] is True
    assert data["command"] == "sources.list"
    assert isinstance(data["data"], list)
    assert len(data["data"]) > 0


def test_sources_list_contains_expected_keys(runner: CliRunner) -> None:
    result = runner.invoke(main, ["--json", "sources", "list"])
    data = json.loads(result.output)
    first = data["data"][0]
    assert "source_key" in first
    assert "is_active" in first
    assert "source_class" in first


# ── sources info ──────────────────────────────────────────────────────────────


def test_sources_info_found(runner: CliRunner) -> None:
    result = runner.invoke(
        main, ["--json", "sources", "info", "saskatoon_police_open_data"]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["ok"] is True
    assert data["data"]["source_key"] == "saskatoon_police_open_data"
    assert data["data"]["source_class"] == "portal_reference"


def test_sources_info_not_found(runner: CliRunner) -> None:
    result = runner.invoke(
        main, ["--json", "sources", "info", "nonexistent_source_xyz"]
    )
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["ok"] is False
    assert data["error_code"] == "SOURCE_NOT_FOUND"
    assert data["command"] == "sources.info"


# ── sources enable / disable ─────────────────────────────────────────────────


def test_sources_enable_requires_yes_flag(runner: CliRunner) -> None:
    """Enable without --yes must be rejected by Click (missing required option)."""
    result = runner.invoke(
        main, ["sources", "enable", "saskatoon_police_open_data"]
    )
    assert result.exit_code != 0


def test_sources_disable_requires_yes_flag(runner: CliRunner) -> None:
    result = runner.invoke(
        main, ["sources", "disable", "saskatoon_police_open_data"]
    )
    assert result.exit_code != 0


def test_sources_enable_not_found(runner: CliRunner) -> None:
    result = runner.invoke(
        main,
        ["--json", "sources", "enable", "nonexistent_xyz", "--yes"],
    )
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["ok"] is False
    assert data["error_code"] == "SOURCE_NOT_FOUND"


def test_sources_disable_not_found(runner: CliRunner) -> None:
    result = runner.invoke(
        main,
        ["--json", "sources", "disable", "nonexistent_xyz", "--yes"],
    )
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["ok"] is False
    assert data["error_code"] == "SOURCE_NOT_FOUND"


def test_sources_enable_portal_reference_rejected(runner: CliRunner) -> None:
    """portal_reference sources must be rejected with SOURCE_NOT_RUNNABLE."""
    result = runner.invoke(
        main, ["--json", "sources", "enable", "saskatoon_open_data_crime", "--yes"]
    )
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["ok"] is False
    assert data["error_code"] == "SOURCE_NOT_RUNNABLE"
    assert data["source_key"] == "saskatoon_open_data_crime"
    assert data["source_class"] == "portal_reference"


def test_sources_enable_disabled_stub_rejected(runner: CliRunner) -> None:
    """disabled_stub sources must be rejected with SOURCE_NOT_RUNNABLE."""
    result = runner.invoke(
        main,
        ["--json", "sources", "enable", "web_monitor_saskatoon_police_news", "--yes"],
    )
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["ok"] is False
    assert data["error_code"] == "SOURCE_NOT_RUNNABLE"
    assert data["source_class"] == "disabled_stub"


def test_sources_enable_machine_ingest_succeeds(runner: CliRunner) -> None:
    """machine_ingest sources can be enabled and then disabled."""
    target = "federal_court_canada"

    enable_result = runner.invoke(
        main, ["--json", "sources", "enable", target, "--yes"]
    )
    assert enable_result.exit_code == 0, enable_result.output
    data = json.loads(enable_result.output)
    assert data["ok"] is True
    assert data["data"]["is_active"] is True

    disable_result = runner.invoke(
        main, ["--json", "sources", "disable", target, "--yes"]
    )
    assert disable_result.exit_code == 0, disable_result.output
    assert json.loads(disable_result.output)["data"]["is_active"] is False


def test_sources_disable_portal_reference_allowed(runner: CliRunner) -> None:
    """disable is allowed for any existing source (including portal_reference)."""
    result = runner.invoke(
        main, ["--json", "sources", "disable", "saskatoon_open_data_crime", "--yes"]
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["ok"] is True
    assert data["data"]["is_active"] is False


def test_sources_enable_json_error_shape_stable(runner: CliRunner) -> None:
    """SOURCE_NOT_RUNNABLE error must include source_key and source_class."""
    result = runner.invoke(
        main, ["--json", "sources", "enable", "saskatoon_police_open_data", "--yes"]
    )
    data = json.loads(result.output)
    assert data["ok"] is False
    assert data["error_code"] == "SOURCE_NOT_RUNNABLE"
    assert "source_key" in data
    assert "source_class" in data
    assert data["next_action"] != ""


# ── ingest run ────────────────────────────────────────────────────────────────


def test_ingest_run_portal_reference_rejected(runner: CliRunner) -> None:
    """portal_reference sources must be rejected with SOURCE_NOT_RUNNABLE."""
    result = runner.invoke(
        main, ["--json", "ingest", "run", "saskatoon_police_open_data"]
    )
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["ok"] is False
    assert data["error_code"] == "SOURCE_NOT_RUNNABLE"
    assert data["source_key"] == "saskatoon_police_open_data"
    assert data["source_class"] == "portal_reference"


def test_ingest_run_source_not_found(runner: CliRunner) -> None:
    result = runner.invoke(
        main, ["--json", "ingest", "run", "nonexistent_source_xyz"]
    )
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["ok"] is False
    assert data["error_code"] == "SOURCE_NOT_FOUND"


def test_ingest_run_disabled_stub_rejected(runner: CliRunner) -> None:
    """disabled_stub sources must be rejected (source_class != machine_ingest)."""
    result = runner.invoke(
        main, ["--json", "ingest", "run", "web_monitor_saskatoon_police_news"]
    )
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["ok"] is False
    assert data["error_code"] == "SOURCE_NOT_RUNNABLE"


# ── ingest status ─────────────────────────────────────────────────────────────


def test_ingest_status_not_found(runner: CliRunner) -> None:
    result = runner.invoke(main, ["--json", "ingest", "status", "999999"])
    assert result.exit_code == 1
    data = json.loads(result.output)
    assert data["ok"] is False
    assert data["error_code"] == "RUN_NOT_FOUND"
    assert data["command"] == "ingest.status"


# ── JSON envelope contract ────────────────────────────────────────────────────


def test_json_success_envelope_shape(runner: CliRunner) -> None:
    """Successful JSON output must have ok, command, data, warnings, errors keys."""
    result = runner.invoke(main, ["--json", "health"])
    data = json.loads(result.output)
    assert set(data.keys()) >= {"ok", "command", "data", "warnings", "errors"}
    assert isinstance(data["warnings"], list)
    assert isinstance(data["errors"], list)


def test_json_error_envelope_shape(runner: CliRunner) -> None:
    """Error JSON output must have ok, command, error_code, message, next_action."""
    result = runner.invoke(
        main, ["--json", "ingest", "run", "saskatoon_police_open_data"]
    )
    data = json.loads(result.output)
    assert set(data.keys()) >= {"ok", "command", "error_code", "message", "next_action"}
    assert data["ok"] is False
