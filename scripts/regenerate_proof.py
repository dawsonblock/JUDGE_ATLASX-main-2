#!/usr/bin/env python3
"""Regenerate proof artifacts on demand.

This script re-runs the proof generation pipeline to update
the proof artifacts in artifacts/proof/current.

Usage:
  python -m scripts.regenerate_proof
  python -m scripts.regenerate_proof --skip-db
  python -m scripts.regenerate_proof --steps check_no_pyc,validate_sources
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass
class StepResult:
    name: str
    command: str
    status: str
    exit_code: int
    duration_seconds: float
    log_path: str


def _run_step(
    repo_root: Path,
    out_dir: Path,
    name: str,
    log_name: str,
    command: list[str],
) -> StepResult:
    log_path = out_dir / log_name
    t0 = datetime.now(timezone.utc)
    with log_path.open("w", encoding="utf-8") as fh:
        proc = subprocess.run(
            command,
            cwd=repo_root,
            stdout=fh,
            stderr=subprocess.STDOUT,
            text=True,
            check=False,
        )
    duration = (datetime.now(timezone.utc) - t0).total_seconds()
    return StepResult(
        name=name,
        command=" ".join(command),
        status="PASS" if proc.returncode == 0 else "FAIL",
        exit_code=proc.returncode,
        duration_seconds=round(duration, 3),
        log_path=str(log_path.relative_to(repo_root)),
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate proof artifacts"
    )
    parser.add_argument(
        "--skip-db",
        action="store_true",
        help="Skip database-dependent proof steps"
    )
    parser.add_argument(
        "--steps",
        type=str,
        help="Comma-separated list of steps to run (default: all)"
    )
    args = parser.parse_args()

    repo_root = Path(__file__).resolve().parents[1]
    out_dir = repo_root / "artifacts" / "proof" / "current"
    out_dir.mkdir(parents=True, exist_ok=True)
    proof_db_url = f"sqlite:///{(out_dir / 'proof.db').resolve()}"

    backend_venv_python = repo_root / "backend" / ".venv" / "bin" / "python"
    python_exe = str(backend_venv_python) if backend_venv_python.exists() else sys.executable

    all_steps: list[tuple[str, str, list[str]]] = [
        ("check_no_pyc", "check_no_pyc.log", ["bash", "scripts/check_no_pyc.sh"]),
        ("check_false_claims", "check_false_claims.log", [python_exe, "scripts/check_false_claims.py"]),
        (
            "check_external_boundaries",
            "check_external_boundaries.log",
            [python_exe, "scripts/check_external_boundaries.py"],
        ),
        (
            "prepare_proof_db",
            "prepare_proof_db.log",
            [python_exe, "scripts/prepare_proof_db.py", "--proof-db", str(out_dir / "proof.db")],
        ),
        ("validate_sources", "validate_sources.log", [python_exe, "backend/tools/validate_sources.py"]),
        (
            "verify_evidence_store",
            "verify_evidence_store.log",
            ["bash", "-lc", f'JTA_DATABASE_URL="{proof_db_url}" {python_exe} backend/tools/verify_evidence_store.py'],
        ),
        (
            "verify_audit_chain",
            "verify_audit_chain.log",
            ["bash", "-lc", f'JTA_DATABASE_URL="{proof_db_url}" {python_exe} backend/tools/verify_audit_chain.py'],
        ),
        (
            "auth_mutation_route_coverage",
            "auth_mutation_route_coverage.log",
            [python_exe, "scripts/auth_mutation_route_coverage.py"],
        ),
        (
            "verify_source_registry",
            "verify_source_registry.log",
            [python_exe, "scripts/verify_source_registry.py"],
        ),
    ]

    # Filter steps based on arguments
    if args.skip_db:
        db_steps = {"prepare_proof_db", "verify_evidence_store", "verify_audit_chain"}
        steps = [(n, l, c) for n, l, c in all_steps if n not in db_steps]
    elif args.steps:
        requested_steps = set(args.steps.split(","))
        steps = [(n, l, c) for n, l, c in all_steps if n in requested_steps]
        if len(steps) != len(requested_steps):
            missing = requested_steps - {n for n, _, _ in steps}
            print(f"Warning: Unknown steps: {missing}", file=sys.stderr)
    else:
        steps = all_steps

    results: list[StepResult] = []
    for name, log_name, command in steps:
        print(f"Running: {name}")
        result = _run_step(repo_root, out_dir, name, log_name, command)
        results.append(result)
        print(f"  Status: {result.status} ({result.duration_seconds}s)")

    # Write summary
    summary = {
        "regenerated_at": datetime.now(timezone.utc).isoformat(),
        "total_steps": len(results),
        "passed": sum(1 for r in results if r.status == "PASS"),
        "failed": sum(1 for r in results if r.status == "FAIL"),
        "steps": [asdict(r) for r in results],
    }

    summary_path = out_dir / "regeneration_summary.json"
    with summary_path.open("w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=2)

    print(f"\nSummary written to: {summary_path}")
    print(f"Passed: {summary['passed']}/{summary['total_steps']}")
    print(f"Failed: {summary['failed']}/{summary['total_steps']}")

    return 1 if summary["failed"] > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
