#!/usr/bin/env python3
"""Verify that repository status and proof references resolve to the current truth layer."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


CANONICAL_CURRENT_PROOF = "artifacts/proof/current/CURRENT_PROOF.md"
CANONICAL_RELEASE_READINESS = "artifacts/proof/current/release_readiness.md"
CANONICAL_STATUS = "STATUS.md"
CANONICAL_RELEASE_GATE = "artifacts/proof/current/release_gate.json"
CANONICAL_GATE_SUMMARY = "artifacts/proof/current/alpha_gate_summary.json"
VALIDATION_SUMMARY = ".validation_logs/validation_summary.json"
LEGACY_RELEASE_READINESS = "artifacts/proof/release_readiness.md"
ARCHIVED_HEADER = "ARCHIVED / NOT CURRENT"

DOCS_TO_CHECK = (
    "README.md",
    "CURRENT_STATUS.md",
    "RELEASE_BLOCKERS.md",
    "PROOF_STATUS.md",
    "docs/RELEASE_READINESS.md",
    "docs/REPO_REALITY.md",
    "docs/DEPLOYMENT.md",
)

POSITIVE_PRODUCTION_READY_PATTERNS = (
    re.compile(r"production\s+ready\s*:\s*true", re.IGNORECASE),
    re.compile(r"\bproduction-ready\b", re.IGNORECASE),
    re.compile(r"ready\s+for\s+production\s+deployment", re.IGNORECASE),
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_line_value(text: str, prefix: str) -> str | None:
    for line in text.splitlines():
        if line.startswith(prefix):
            return line.split(":", 1)[1].strip()
    return None


def _has_positive_production_ready_claim(text: str) -> bool:
    lowered = text.lower()
    if "production ready: false" in lowered:
        lowered = lowered.replace("production ready: false", "")
    if "production_ready: false" in lowered:
        lowered = lowered.replace("production_ready: false", "")
    if "production-ready=false until all production gates pass." in lowered:
        lowered = lowered.replace("production-ready=false until all production gates pass.", "")
    if "not ready for production deployment" in lowered:
        lowered = lowered.replace("not ready for production deployment", "")
    if "not production ready" in lowered:
        lowered = lowered.replace("not production ready", "")
    return any(pattern.search(lowered) for pattern in POSITIVE_PRODUCTION_READY_PATTERNS)


def verify(root: Path) -> list[str]:
    errors: list[str] = []

    status_path = root / CANONICAL_STATUS
    if not status_path.exists():
        errors.append(f"missing:{CANONICAL_STATUS}")
        return errors

    status_text = _read(status_path)

    # ------------------------------------------------------------
    # Validate STATUS.md against the CANONICAL release_gate.json.
    # Do not hard-require PASS — instead enforce that STATUS.md
    # never claims PASS when release_gate.json says otherwise.
    # ------------------------------------------------------------
    release_gate_path = root / CANONICAL_RELEASE_GATE
    rg_passed: bool | None = None
    if not release_gate_path.exists():
        errors.append(f"missing:{CANONICAL_RELEASE_GATE}")
    else:
        try:
            rg = json.loads(release_gate_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            rg = {}
        rg_passed = rg.get("alpha_gate_passed")
        if rg_passed is False and "Alpha proof status: PASS" in status_text:
            errors.append(
                "STATUS.md:false_pass_claim:release_gate.json says alpha_gate_passed=false"
            )
        if rg_passed is False and "Alpha readiness status: PASS" in status_text:
            errors.append(
                "STATUS.md:false_readiness_claim:release_gate.json says alpha_gate_passed=false"
            )

    # Validate STATUS.md against validation summary outcomes when available.
    validation_summary_path = root / VALIDATION_SUMMARY
    if validation_summary_path.exists():
        try:
            validation_summary = json.loads(
                validation_summary_path.read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            validation_summary = {}

        overall_status = str(
            validation_summary.get("overall_status", "")
        ).strip().lower()
        phases = validation_summary.get("phases")
        if not isinstance(phases, dict):
            phases = {}

        failed_phase_names = [
            name
            for name, state in phases.items()
            if str(state).strip().lower() == "failed"
        ]
        failed_phase_list = ",".join(sorted(failed_phase_names)) or "unknown"

        if overall_status == "failed":
            if "Alpha proof status: PASS" in status_text:
                errors.append(
                    "STATUS.md:false_pass_claim:"
                    "validation_summary.json says overall_status=failed"
                    f" phases={failed_phase_list}"
                )
            if "Alpha readiness status: PASS" in status_text:
                errors.append(
                    "STATUS.md:false_readiness_claim:"
                    "validation_summary.json says overall_status=failed"
                    f" phases={failed_phase_list}"
                )
            if rg_passed is True:
                errors.append(
                    "release_gate.json:validation_contradiction:"
                    "alpha_gate_passed=true while "
                    "validation_summary.json overall_status=failed"
                    f" phases={failed_phase_list}"
                )

    # Validate alpha_gate_summary.json honesty: PASS must not appear when frontend was skipped.
    gate_summary_path = root / CANONICAL_GATE_SUMMARY
    if gate_summary_path.exists():
        try:
            gs = json.loads(gate_summary_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            gs = {}
        if gs.get("alpha_gate_pass") is True and gs.get("frontend_tests_passed") == "not_run":
            errors.append(
                "alpha_gate_summary.json:false_pass:alpha_gate_pass=true but frontend_tests_passed=not_run"
            )

    if "Production ready: FALSE" not in status_text:
        errors.append("STATUS.md:missing_production_false_line")
    if "**Alpha gate checks**: see artifacts/proof/current/release_gate.json" not in status_text:
        errors.append("STATUS.md:missing_alpha_gate_authority_line")
    if (
        "This repository is an alpha/research-grade platform, not a production legal system."
        not in status_text
    ):
        errors.append("STATUS.md:missing_required_research_grade_disclaimer")
    if "## Gate Interpretation" not in status_text:
        errors.append("STATUS.md:missing_gate_interpretation_section")

    status_alpha = _extract_line_value(status_text, "- Alpha proof status")
    status_prod = _extract_line_value(status_text, "- Production ready")

    production_proof = root / "artifacts" / "proof" / "current" / "production_preflight.md"

    for rel_path in DOCS_TO_CHECK:
        path = root / rel_path
        if not path.exists():
            errors.append(f"missing:{rel_path}")
            continue
        text = _read(path)
        if LEGACY_RELEASE_READINESS in text:
            errors.append(f"{rel_path}:stale_release_readiness_reference")
        if CANONICAL_STATUS not in text:
            errors.append(f"{rel_path}:missing_status_reference")
        if CANONICAL_CURRENT_PROOF not in text:
            errors.append(f"{rel_path}:missing_current_proof_reference")
        if CANONICAL_RELEASE_READINESS not in text:
            errors.append(f"{rel_path}:missing_current_release_readiness_reference")
        if _has_positive_production_ready_claim(text) and not production_proof.exists():
            errors.append(f"{rel_path}:production_ready_claim_without_proof")

    current_status_path = root / "CURRENT_STATUS.md"
    if current_status_path.exists():
        current_status_text = _read(current_status_path)
        if "## Canonical Authority" not in current_status_text:
            errors.append("CURRENT_STATUS.md:missing_canonical_authority_section")
        if "Gate status authority: artifacts/proof/current/release_gate.json" not in current_status_text:
            errors.append("CURRENT_STATUS.md:missing_gate_authority_reference")
        current_alpha = _extract_line_value(current_status_text, "- Alpha proof status")
        current_prod = _extract_line_value(current_status_text, "- Production ready")
        if current_alpha is not None and status_alpha is not None and current_alpha != status_alpha:
            errors.append("CURRENT_STATUS.md:alpha_status_contradicts_STATUS.md")
        if current_prod is not None and status_prod is not None and current_prod != status_prod:
            errors.append("CURRENT_STATUS.md:production_status_contradicts_STATUS.md")

    release_blockers_path = root / "RELEASE_BLOCKERS.md"
    if release_blockers_path.exists():
        release_blockers_text = _read(release_blockers_path)
        if "## Alpha Gate Status" not in release_blockers_text:
            errors.append("RELEASE_BLOCKERS.md:missing_alpha_gate_status_section")
        if "Source-of-truth blocker state is defined by artifacts/proof/current/release_gate.json." not in release_blockers_text:
            errors.append("RELEASE_BLOCKERS.md:missing_release_gate_reference")
        if "Alpha gate pass/fail is not a production readiness claim." not in release_blockers_text:
            errors.append("RELEASE_BLOCKERS.md:missing_gate_vs_production_disclaimer")

    proof_status_path = root / "PROOF_STATUS.md"
    if proof_status_path.exists():
        proof_status_text = _read(proof_status_path)
        if "## Authority Notes" not in proof_status_text:
            errors.append("PROOF_STATUS.md:missing_authority_notes_section")
        if "Canonical machine truth is artifacts/proof/current/release_gate.json." not in proof_status_text:
            errors.append("PROOF_STATUS.md:missing_release_gate_authority_line")

    legacy_release_path = root / LEGACY_RELEASE_READINESS
    if legacy_release_path.exists():
        legacy_text = _read(legacy_release_path)
        if ARCHIVED_HEADER not in legacy_text:
            errors.append("artifacts/proof/release_readiness.md:live_unarchived_legacy_file")

    proof_policy_path = root / "docs" / "PROOF_POLICY.md"
    if proof_policy_path.exists() and _has_positive_production_ready_claim(_read(proof_policy_path)) and not production_proof.exists():
        errors.append("docs/PROOF_POLICY.md:production_ready_claim_without_proof")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    errors = verify(root)
    if errors:
        print("STATUS CONSISTENCY: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    print("STATUS CONSISTENCY: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())