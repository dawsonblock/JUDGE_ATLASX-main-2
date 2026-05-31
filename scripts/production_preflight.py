#!/usr/bin/env python3
"""Run production-only readiness checks without mutating state."""

from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = (
    REPO_ROOT / "artifacts" / "proof" / "current" / "production_preflight.md"
)

WEAK_SECRET_MARKERS = {
    "changeme",
    "change-me",
    "default",
    "dev",
    "development",
    "test",
    "example",
}


class ResolvedEnvValue:
    def __init__(
        self,
        primary_name: str,
        value: str,
        source_name: str | None,
        deprecated_alias_used: bool = False,
        deprecated_alias_name: str | None = None,
    ) -> None:
        self.primary_name = primary_name
        self.value = value
        self.source_name = source_name
        self.deprecated_alias_used = deprecated_alias_used
        self.deprecated_alias_name = deprecated_alias_name


ENV_SOURCES = {
    "app_env": ("JTA_APP_ENV", ("APP_ENV", "ENVIRONMENT"), "development"),
    "jwt_secret_key": ("JTA_JWT_SECRET_KEY", ("JTA_JWT_SECRET",), ""),
    "database_url": ("JTA_DATABASE_URL", ("DATABASE_URL",), ""),
    "redis_url": ("JTA_REDIS_URL", ("REDIS_URL",), ""),
    "evidence_store_root": (
        "JTA_EVIDENCE_STORE_ROOT",
        ("EVIDENCE_STORE_ROOT",),
        "",
    ),
    "cors_origins": ("JTA_CORS_ORIGINS", ("CORS_ALLOWLIST",), ""),
    "backup_policy": ("JTA_BACKUP_POLICY", ("BACKUP_POLICY",), ""),
}


def _resolve_env_value(
    primary_name: str,
    aliases: tuple[str, ...],
    default: str = "",
) -> ResolvedEnvValue:
    for source_name in (primary_name, *aliases):
        raw_value = os.getenv(source_name)
        if raw_value is None:
            continue
        value = raw_value.strip()
        if not value:
            continue
        return ResolvedEnvValue(
            primary_name=primary_name,
            value=value,
            source_name=source_name,
            deprecated_alias_used=source_name != primary_name,
            deprecated_alias_name=(
                source_name if source_name != primary_name else None
            ),
        )

    return ResolvedEnvValue(
        primary_name=primary_name,
        value=default,
        source_name=primary_name if default else None,
        deprecated_alias_used=False,
        deprecated_alias_name=None,
    )


def resolve_runtime_env() -> tuple[dict[str, ResolvedEnvValue], list[str]]:
    resolved: dict[str, ResolvedEnvValue] = {}
    warnings: list[str] = []
    for key, (primary_name, aliases, default) in ENV_SOURCES.items():
        resolved_value = _resolve_env_value(primary_name, aliases, default)
        resolved[key] = resolved_value
        if (
            resolved_value.deprecated_alias_used
            and resolved_value.deprecated_alias_name
        ):
            warnings.append(
                f"{resolved_value.deprecated_alias_name} is deprecated; use "
                f"{resolved_value.primary_name}"
            )
    return resolved, warnings


def _is_weak_secret(value: str | None) -> bool:
    if not value:
        return True
    lowered = value.strip().lower()
    if len(value) < 32:
        return True
    return any(marker in lowered for marker in WEAK_SECRET_MARKERS)


def _bool_env(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _check(name: str, passed: bool, details: str) -> dict:
    return {"name": name, "passed": passed, "details": details}


def _source_label(resolved: ResolvedEnvValue) -> str:
    return resolved.source_name or resolved.primary_name


def run_checks(
    allow_repo_evidence_store: bool = False,
    runtime_env: dict[str, ResolvedEnvValue] | None = None,
) -> list[dict]:
    if runtime_env is None:
        runtime_env, _warnings = resolve_runtime_env()

    env = runtime_env["app_env"].value
    evidence_root = runtime_env["evidence_store_root"].value
    cors_allowlist = runtime_env["cors_origins"].value
    egress_proxy = os.getenv("JTA_FETCH_EGRESS_PROXY", "").strip()
    db_url = runtime_env["database_url"].value
    backup_policy = runtime_env["backup_policy"].value

    checks: list[dict] = []
    app_env_label = _source_label(runtime_env["app_env"])
    jwt_secret_label = _source_label(runtime_env["jwt_secret_key"])
    redis_label = _source_label(runtime_env["redis_url"])
    evidence_label = _source_label(runtime_env["evidence_store_root"])
    cors_label = _source_label(runtime_env["cors_origins"])
    database_label = _source_label(runtime_env["database_url"])
    backup_label = _source_label(runtime_env["backup_policy"])

    checks.append(
        _check(
            "production_environment_selected",
            env.lower() in {"prod", "production"},
            f"{app_env_label}={env}",
        )
    )

    jwt_secret = runtime_env["jwt_secret_key"].value
    checks.append(
        _check(
            "strong_jwt_secret",
            not _is_weak_secret(jwt_secret),
            f"{jwt_secret_label} must be set and >= 32 chars, non-default",
        )
    )

    checks.append(
        _check(
            "legacy_admin_token_disabled",
            not _bool_env("JTA_ENABLE_LEGACY_ADMIN_TOKEN"),
            "JTA_ENABLE_LEGACY_ADMIN_TOKEN must be false in production",
        )
    )

    checks.append(
        _check(
            "redis_rate_limit_configured",
            bool(runtime_env["redis_url"].value),
            f"{redis_label} must be configured",
        )
    )

    evidence_path = Path(evidence_root) if evidence_root else None
    checks.append(
        _check(
            "evidence_store_root_configured",
            bool(evidence_root),
            f"{evidence_label}={evidence_root or 'unset'}",
        )
    )

    if evidence_path:
        checks.append(
            _check(
                "evidence_store_exists",
                evidence_path.exists(),
                str(evidence_path),
            )
        )
        checks.append(
            _check(
                "evidence_store_writable",
                os.access(evidence_path, os.W_OK),
                str(evidence_path),
            )
        )
        inside_repo = (
            evidence_path.is_absolute()
            and evidence_path.resolve().is_relative_to(REPO_ROOT)
        )
        checks.append(
            _check(
                "evidence_store_outside_repo",
                (not inside_repo) or allow_repo_evidence_store,
                f"inside_repo={inside_repo}",
            )
        )

    checks.append(
        _check(
            "cors_allowlist_not_wildcard",
            bool(cors_allowlist) and cors_allowlist != "*",
            f"{cors_label}={cors_allowlist or 'unset'}",
        )
    )

    checks.append(
        _check(
            "egress_proxy_configured",
            bool(egress_proxy)
            or _bool_env("JTA_ALLOW_DIRECT_FETCH_IN_NON_PROD"),
            (
                "JTA_FETCH_EGRESS_PROXY required unless "
                "JTA_ALLOW_DIRECT_FETCH_IN_NON_PROD=true"
            ),
        )
    )

    checks.append(
        _check(
            "database_url_configured",
            bool(db_url),
            f"{database_label} must be set",
        )
    )
    checks.append(
        _check(
            "debug_mode_disabled",
            not _bool_env("DEBUG"),
            "DEBUG must be false",
        )
    )
    checks.append(
        _check(
            "backup_policy_configured",
            bool(backup_policy),
            f"{backup_label} must be documented/configured",
        )
    )

    return checks


def write_report(
    checks: list[dict],
    output_path: Path,
    *,
    runtime_env: dict[str, ResolvedEnvValue] | None = None,
    warnings: list[str] | None = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    passed = sum(1 for check in checks if check["passed"])
    failed = len(checks) - passed
    lines = [
        "# Production Preflight",
        "",
        f"- generated_at: {datetime.now(timezone.utc).isoformat()}",
        f"- checks_total: {len(checks)}",
        f"- checks_passed: {passed}",
        f"- checks_failed: {failed}",
        f"- production_preflight_passed: {'true' if failed == 0 else 'false'}",
        "",
        "## Checks",
        "",
    ]
    if runtime_env:
        lines.extend(["## Environment Sources", ""])
        for key in sorted(runtime_env):
            resolved = runtime_env[key]
            source_name = resolved.source_name or "unset"
            lines.append(f"- {key}: {source_name}")
        if warnings:
            lines.extend(["", "## Deprecated Aliases", ""])
            for warning in warnings:
                lines.append(f"- {warning}")
        lines.append("")
    for check in checks:
        status = "PASS" if check["passed"] else "FAIL"
        lines.append(f"- {status} {check['name']}: {check['details']}")

    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expect-fail-in-dev", action="store_true")
    parser.add_argument("--allow-repo-evidence-store", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    runtime_env, warnings = resolve_runtime_env()
    checks = run_checks(
        allow_repo_evidence_store=args.allow_repo_evidence_store,
        runtime_env=runtime_env,
    )
    write_report(
        checks,
        OUTPUT_PATH,
        runtime_env=runtime_env,
        warnings=warnings,
    )

    failed = [check for check in checks if not check["passed"]]
    payload = {
        "production_preflight_passed": len(failed) == 0,
        "failed_checks": [check["name"] for check in failed],
        "report": str(OUTPUT_PATH),
        "env_sources": {
            key: {
                "primary_name": resolved.primary_name,
                "source_name": resolved.source_name,
                "deprecated_alias_used": resolved.deprecated_alias_used,
                "deprecated_alias_name": resolved.deprecated_alias_name,
            }
            for key, resolved in runtime_env.items()
        },
        "deprecated_env_aliases": warnings,
    }

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(f"Production preflight report written: {OUTPUT_PATH}")
        print("PASS" if not failed else "FAIL")

    if failed and args.expect_fail_in_dev:
        return 0
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
