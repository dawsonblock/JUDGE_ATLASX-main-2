from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[3] / "scripts" / "production_preflight.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "production_preflight",
        SCRIPT_PATH,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_dev_defaults_fail_preflight(monkeypatch):
    module = _load_module()
    monkeypatch.delenv("JTA_APP_ENV", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("JTA_JWT_SECRET_KEY", raising=False)
    monkeypatch.delenv("JTA_JWT_SECRET", raising=False)
    monkeypatch.delenv("JTA_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("CORS_ALLOWLIST", raising=False)
    monkeypatch.delenv("JTA_EVIDENCE_STORE_ROOT", raising=False)
    monkeypatch.delenv("EVIDENCE_STORE_ROOT", raising=False)

    checks = module.run_checks()

    failed = {check["name"] for check in checks if not check["passed"]}
    assert "production_environment_selected" in failed
    assert "strong_jwt_secret" in failed
    assert "cors_allowlist_not_wildcard" in failed
    assert "evidence_store_root_configured" in failed


def test_weak_secret_fails(monkeypatch):
    module = _load_module()
    monkeypatch.setenv("JTA_JWT_SECRET_KEY", "changeme")

    checks = module.run_checks()

    result = next(
        check for check in checks if check["name"] == "strong_jwt_secret"
    )
    assert result["passed"] is False


def test_wildcard_cors_fails(monkeypatch):
    module = _load_module()
    monkeypatch.setenv("JTA_CORS_ORIGINS", "*")

    checks = module.run_checks()

    result = next(
        check
        for check in checks
        if check["name"] == "cors_allowlist_not_wildcard"
    )
    assert result["passed"] is False


def test_evidence_store_inside_repo_fails_by_default(monkeypatch):
    module = _load_module()
    inside_repo = str(module.REPO_ROOT / "artifacts")
    monkeypatch.setenv("JTA_EVIDENCE_STORE_ROOT", inside_repo)

    checks = module.run_checks(allow_repo_evidence_store=False)

    result = next(
        check
        for check in checks
        if check["name"] == "evidence_store_outside_repo"
    )
    assert result["passed"] is False


def test_evidence_store_inside_repo_can_be_overridden(monkeypatch):
    module = _load_module()
    inside_repo = str(module.REPO_ROOT / "artifacts")
    monkeypatch.setenv("JTA_EVIDENCE_STORE_ROOT", inside_repo)

    checks = module.run_checks(allow_repo_evidence_store=True)

    result = next(
        check
        for check in checks
        if check["name"] == "evidence_store_outside_repo"
    )
    assert result["passed"] is True


def test_active_jta_names_are_honored_and_reported(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_module()
    evidence_root = tmp_path / "evidence"
    evidence_root.mkdir()

    monkeypatch.setenv("JTA_APP_ENV", "production")
    monkeypatch.setenv(
        "JTA_JWT_SECRET_KEY",
        "7f4c1d9e2a8b6c0d5e9f3a1b4c7d8e0f9a2b6c5d",
    )
    monkeypatch.setenv("JTA_CORS_ORIGINS", "https://example.com")
    monkeypatch.setenv("JTA_DATABASE_URL", "sqlite:///./test.db")
    monkeypatch.setenv("JTA_REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("JTA_EVIDENCE_STORE_ROOT", str(evidence_root))
    monkeypatch.setenv("JTA_FETCH_EGRESS_PROXY", "http://proxy.local:8080")
    monkeypatch.setenv("JTA_BACKUP_POLICY", "daily-backup")
    monkeypatch.setenv("JTA_ENABLE_LEGACY_ADMIN_TOKEN", "false")

    runtime_env, warnings = module.resolve_runtime_env()
    checks = module.run_checks(runtime_env=runtime_env)

    failed = {check["name"] for check in checks if not check["passed"]}
    assert failed == set()
    assert warnings == []
    assert runtime_env["jwt_secret_key"].source_name == "JTA_JWT_SECRET_KEY"
    assert runtime_env["cors_origins"].source_name == "JTA_CORS_ORIGINS"


def test_deprecated_aliases_emit_warnings(monkeypatch) -> None:
    module = _load_module()

    monkeypatch.delenv("JTA_APP_ENV", raising=False)
    monkeypatch.delenv("JTA_JWT_SECRET_KEY", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv(
        "JTA_JWT_SECRET",
        "7f4c1d9e2a8b6c0d5e9f3a1b4c7d8e0f9a2b6c5d",
    )
    monkeypatch.setenv("CORS_ALLOWLIST", "https://example.com")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///./test.db")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv(
        "EVIDENCE_STORE_ROOT",
        str(module.REPO_ROOT / "artifacts"),
    )
    monkeypatch.setenv("BACKUP_POLICY", "daily-backup")

    runtime_env, warnings = module.resolve_runtime_env()

    assert runtime_env["app_env"].source_name == "APP_ENV"
    assert runtime_env["jwt_secret_key"].source_name == "JTA_JWT_SECRET"
    assert runtime_env["cors_origins"].source_name == "CORS_ALLOWLIST"
    assert any("APP_ENV is deprecated" in warning for warning in warnings)
    assert any(
        "JTA_JWT_SECRET is deprecated" in warning for warning in warnings
    )
    assert any(
        "CORS_ALLOWLIST is deprecated" in warning for warning in warnings
    )
