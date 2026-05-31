#!/usr/bin/env python3
"""Fail when human-authored status narratives contradict canonical release truth."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

CANONICAL_RELEASE_GATE = Path("artifacts/proof/current/release_gate.json")
CANONICAL_RELEASE_READINESS = Path("artifacts/proof/current/release_readiness.md")

ROOT_STATUS_DOCS = (
    Path("STATUS.md"),
    Path("CURRENT_STATUS.md"),
    Path("REPAIR_STATUS.md"),
    Path("PROOF_STATUS.md"),
    Path("RELEASE_BLOCKERS.md"),
    Path("README.md"),
)

REQUIRED_MATRIX_KEYS = (
    "alpha_ready",
    "production_ready",
    "public_release_safe",
    "ingestion_coverage",
    "AI_answering_enabled",
    "workflow_admin_enabled",
    "live_map_enabled",
)

PRODUCTION_WARNING = "Production-ready=false until all production gates pass."

PRODUCTION_TRUE_PATTERNS = (
    re.compile(r"\bproduction[_ -]?ready\s*[:=]\s*true\b", re.IGNORECASE),
    re.compile(r"\bready for production deployment\b", re.IGNORECASE),
    re.compile(r"\bproduction release is ready\b", re.IGNORECASE),
)

ALPHA_FALSE_PATTERNS = (
    re.compile(r"\balpha[_ -]?gate[_ -]?passed\s*[:=]\s*false\b", re.IGNORECASE),
    re.compile(r"\balpha[_ -]?ready\s*[:=]\s*false\b", re.IGNORECASE),
    re.compile(r"\balpha\s+gate\s*[:=]\s*failed\b", re.IGNORECASE),
    re.compile(r"\balpha\s+proof\s+status\s*[:=]\s*fail(?:ed)?\b", re.IGNORECASE),
)

STALE_REPAIR_PATTERNS = (
    re.compile(r"\balpha[_ -]?gate[_ -]?passed\s*[:=]\s*false\b", re.IGNORECASE),
    re.compile(r"\balpha\s+gate\s*[:=]\s*failed\b", re.IGNORECASE),
)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _load_release_gate(path: Path) -> dict:
    if not path.exists():
        raise RuntimeError(f"missing:{path.as_posix()}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"invalid_json_object:{path.as_posix()}")
    return data


def _parse_readiness_bool(text: str, key: str) -> bool | None:
    match = re.search(rf"^\s*-\s*{re.escape(key)}\s*:\s*(true|false)\s*$", text, re.IGNORECASE | re.MULTILINE)
    if not match:
        return None
    return match.group(1).lower() == "true"


def _has_any_pattern(text: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def _scan_stale_repair_status(root: Path) -> list[str]:
    errors: list[str] = []
    skip_parts = {
        ".git",
        "node_modules",
        ".venv",
        "docs/history",
        "artifacts/history",
        "artifacts/proof/current",
        "external_reference",
    }

    for path in root.rglob("*.md"):
        rel = path.relative_to(root).as_posix()
        if any(rel == prefix or rel.startswith(prefix + "/") for prefix in skip_parts):
            continue
        text = _read_text(path)
        for idx, line in enumerate(text.splitlines(), start=1):
            if any(pattern.search(line) for pattern in STALE_REPAIR_PATTERNS):
                errors.append(f"stale_repair_status_outside_history:{rel}:{idx}")
    return errors


def verify(root: Path) -> list[str]:
    errors: list[str] = []

    gate = _load_release_gate(root / CANONICAL_RELEASE_GATE)
    release_readiness_path = root / CANONICAL_RELEASE_READINESS
    if not release_readiness_path.exists():
        errors.append(f"missing:{CANONICAL_RELEASE_READINESS.as_posix()}")
        release_readiness_text = ""
    else:
        release_readiness_text = _read_text(release_readiness_path)

    alpha_gate_passed = gate.get("alpha_gate_passed")
    production_ready = gate.get("production_ready")

    if not isinstance(alpha_gate_passed, bool):
        errors.append("release_gate_invalid:alpha_gate_passed_not_bool")
    if not isinstance(production_ready, bool):
        errors.append("release_gate_invalid:production_ready_not_bool")

    readiness_production_ready = _parse_readiness_bool(release_readiness_text, "production_ready")
    if isinstance(production_ready, bool):
        if readiness_production_ready is None:
            errors.append("release_readiness_missing:production_ready")
        elif readiness_production_ready != production_ready:
            errors.append(
                "release_readiness_contradiction:production_ready_mismatch"
                f":gate={str(production_ready).lower()}"
                f":readiness={str(readiness_production_ready).lower()}"
            )

    if isinstance(alpha_gate_passed, bool):
        readiness_status_line = _parse_readiness_overall_status(release_readiness_text)
        if readiness_status_line is None:
            errors.append("release_readiness_missing:overall_status")
        elif alpha_gate_passed and "pass" not in readiness_status_line:
            errors.append(
                "release_readiness_contradiction:overall_status_not_pass_while_alpha_passed"
            )
        elif (not alpha_gate_passed) and "pass" in readiness_status_line:
            errors.append(
                "release_readiness_contradiction:overall_status_pass_while_alpha_failed"
            )

    for rel_path in ROOT_STATUS_DOCS:
        path = root / rel_path
        if not path.exists():
            errors.append(f"missing:{rel_path.as_posix()}")
            continue
        text = _read_text(path)

        if "artifacts/proof/current/release_gate.json" not in text:
            errors.append(f"missing_release_gate_authority:{rel_path.as_posix()}")

        if rel_path in {
            Path("STATUS.md"),
            Path("CURRENT_STATUS.md"),
            Path("REPAIR_STATUS.md"),
            Path("PROOF_STATUS.md"),
            Path("RELEASE_BLOCKERS.md"),
        }:
            if PRODUCTION_WARNING not in text:
                errors.append(f"missing_required_warning:{rel_path.as_posix()}")

        if rel_path in {Path("STATUS.md"), Path("CURRENT_STATUS.md")}:
            for key in REQUIRED_MATRIX_KEYS:
                if re.search(rf"^\s*-\s*{re.escape(key)}\s*:", text, re.MULTILINE) is None:
                    errors.append(f"missing_status_matrix_key:{rel_path.as_posix()}:{key}")

        if production_ready is False and _has_any_pattern(text, PRODUCTION_TRUE_PATTERNS):
            errors.append(f"production_truth_contradiction:{rel_path.as_posix()}:gate_false_doc_claims_true")

        if alpha_gate_passed is True and _has_any_pattern(text, ALPHA_FALSE_PATTERNS):
            errors.append(f"alpha_truth_contradiction:{rel_path.as_posix()}:gate_true_doc_claims_false")

    errors.extend(_scan_stale_repair_status(root))

    return errors


def _parse_readiness_overall_status(text: str) -> str | None:
    match = re.search(r"^\s*-\s*overall_status\s*:\s*([^\n]+)$", text, re.IGNORECASE | re.MULTILINE)
    if not match:
        return None
    return match.group(1).strip().lower()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    errors = verify(root)
    if errors:
        print("STATUS TRUTH CONSISTENCY: FAIL")
        for error in errors:
            print(f"- {error}")
        return 1

    print("STATUS TRUTH CONSISTENCY: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
