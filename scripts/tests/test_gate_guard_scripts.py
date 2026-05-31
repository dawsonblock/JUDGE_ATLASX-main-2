"""Regression tests for release gate helper scripts."""

from __future__ import annotations

import sys
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from check_dockerfile_copy_paths import _extract_sources_from_instruction
from check_compose_auth_defaults import check as check_compose_auth_defaults
from release_gate import GateStep, _enforce_canlii_staging_gate


def _make_canlii_step() -> GateStep:
    return GateStep(
        name="canlii_staging_proof",
        command="python scripts/prove_canlii_staging.py",
        status="PASS",
        exit_code=0,
        duration_seconds=0.1,
        log_path="artifacts/proof/current/canlii_staging_proof.log",
        started_at_utc="2026-01-01T00:00:00+00:00",
        finished_at_utc="2026-01-01T00:00:01+00:00",
        required=True,
        cwd=".",
    )


def test_extract_sources_handles_copy_link_boolean_flag() -> None:
    sources = _extract_sources_from_instruction("COPY --link missing.txt /app/")
    assert sources == ["missing.txt"]


def test_extract_sources_handles_copy_link_with_other_flags() -> None:
    sources = _extract_sources_from_instruction(
        "COPY --link --chown=1000:1000 src/ dst/"
    )
    assert sources == ["src/"]


def test_canlii_gate_blocks_skipped_status() -> None:
    step = _make_canlii_step()
    checks_map = {"canlii_staging_proof": step}
    blocked_checks: dict[str, str] = {}

    _enforce_canlii_staging_gate(checks_map, blocked_checks, "SKIPPED_NO_API_KEY")

    assert step.status == "BLOCKED"
    assert step.exit_code == 1
    assert step.failure_reason == "missing_canlii_api_key"
    assert "canlii_staging_proof" in blocked_checks


def test_canlii_gate_keeps_pass_status() -> None:
    step = _make_canlii_step()
    checks_map = {"canlii_staging_proof": step}
    blocked_checks: dict[str, str] = {}

    _enforce_canlii_staging_gate(checks_map, blocked_checks, "PASS")

    assert step.status == "PASS"
    assert step.exit_code == 0
    assert blocked_checks == {}


def test_compose_guard_blocks_mandatory_legacy_tokens(tmp_path: Path) -> None:
        compose = tmp_path / "docker-compose.yml"
        compose.write_text(
                """
services:
    backend:
        environment:
            JTA_ENABLE_LEGACY_ADMIN_TOKEN: \"false\"
            JTA_ADMIN_TOKEN: \"${JTA_ADMIN_TOKEN:?must-set}\"
            JTA_ADMIN_REVIEW_TOKEN: \"${JTA_ADMIN_REVIEW_TOKEN:?must-set}\"
""".strip()
                + "\n",
                encoding="utf-8",
        )

        assert check_compose_auth_defaults(compose) == 1
