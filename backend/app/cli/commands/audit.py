"""judgectl audit — CI guard runners."""
from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path

import click

from app.cli.output import emit

_PROJECT_ROOT = Path(__file__).parents[4]
_SCRIPT_DIR = _PROJECT_ROOT / "scripts"


def _run_script_guard(name: str, script: Path, *args: str) -> dict:
    """Run a single guard script and return a structured check result dict."""
    if not script.exists():
        return {
            "name": name,
            "ok": False,
            "detail": f"Script not found: {script}",
        }
    env = {
        **os.environ,
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPYCACHEPREFIX": "",
    }
    result = subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(_PROJECT_ROOT),
    )
    ok = result.returncode == 0
    detail = (result.stdout.strip() or result.stderr.strip())[:500]
    return {
        "name": name,
        "ok": ok,
        "detail": detail,
    }


def _run_shell_guard(name: str, script: Path) -> dict:
    """Run a shell guard script and return a structured check result dict."""
    if not script.exists():
        return {
            "name": name,
            "ok": False,
            "detail": f"Script not found: {script}",
        }
    result = subprocess.run(
        ["bash", str(script)],
        capture_output=True,
        text=True,
        cwd=str(_PROJECT_ROOT),
    )
    ok = result.returncode == 0
    detail = (result.stdout.strip() or result.stderr.strip())[:500]
    return {
        "name": name,
        "ok": ok,
        "detail": detail,
    }


def _run_compileall_guard() -> dict:
    """Run Python compile check on the backend app directory.

    Uses PYTHONPYCACHEPREFIX to redirect all .pyc files to a temporary
    directory so the check never creates __pycache__ in the source tree.
    This ensures check_no_pyc.sh passes regardless of proof command order.
    """
    import tempfile

    app_dir = _PROJECT_ROOT / "backend" / "app"
    scripts_dir = _PROJECT_ROOT / "scripts"
    with tempfile.TemporaryDirectory() as pycache_dir:
        env = {**os.environ, "PYTHONPYCACHEPREFIX": pycache_dir}
        result = subprocess.run(
            [
                sys.executable,
                "-m", "compileall",
                "-q",
                str(app_dir),
                str(scripts_dir),
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(_PROJECT_ROOT),
        )
    ok = result.returncode == 0
    detail = "Python compile check passed" if ok else (result.stderr.strip() or result.stdout.strip())[:500]
    return {
        "name": "compileall",
        "ok": ok,
        "detail": detail,
    }


def _run_cli_availability_guard() -> dict:
    """Check that judgectl is installed and responds to --help."""
    venv_cli = Path(sys.executable).parent / "judgectl"
    cli_cmd = str(venv_cli) if venv_cli.exists() else "judgectl"
    result = subprocess.run(
        [cli_cmd, "--help"],
        capture_output=True,
        text=True,
    )
    ok = result.returncode == 0 and "judgectl" in result.stdout.lower()
    return {
        "name": "cli_availability",
        "ok": ok,
        "detail": "judgectl --help succeeded" if ok else result.stderr.strip()[:200],
    }


@click.group()
def audit() -> None:
    """CI guard runners."""


@audit.command("guards")
@click.pass_context
def audit_guards(ctx: click.Context) -> None:
    """Run all CI guard scripts and report pass/fail.

    Expected JSON output::

        {
          "ok": true,
          "command": "audit.guards",
          "checks": [
            {"name": "validate_workflows", "ok": true},
            {"name": "check_no_pyc", "ok": true},
            {"name": "check_source_keys", "ok": true},
            {"name": "check_statuses", "ok": true},
            {"name": "compileall", "ok": true},
            {"name": "cli_availability", "ok": true}
          ],
          "errors": []
        }
    """
    as_json: bool = ctx.obj.get("as_json", False)

    checks = [
        _run_script_guard(
            "validate_workflows",
            _SCRIPT_DIR / "validate_workflows.py",
        ),
        _run_shell_guard(
            "check_no_pyc",
            _SCRIPT_DIR / "check_no_pyc.sh",
        ),
        _run_script_guard(
            "check_source_keys",
            _SCRIPT_DIR / "check_source_keys.py",
            "--root", "backend/app",
            "--repo-root", ".",
        ),
        _run_script_guard(
            "check_statuses",
            _SCRIPT_DIR / "check_statuses.py",
            "--root", "backend/app",
        ),
        _run_compileall_guard(),
        _run_cli_availability_guard(),
    ]

    all_ok = all(c["ok"] for c in checks)
    errors = [c["detail"] for c in checks if not c["ok"]]

    emit(
        {
            "checks": [{"name": c["name"], "ok": c["ok"]} for c in checks],
            "all_passed": all_ok,
            "errors": errors,
        },
        ok=all_ok,
        command="audit.guards",
        as_json=as_json,
    )
    if not all_ok:
        raise SystemExit(1)


@audit.command("proof")
@click.option(
    "--out-json",
    default="artifacts/proof/latest.json",
    show_default=True,
    help="Path to write proof JSON.",
)
@click.option(
    "--out-md",
    default="artifacts/proof/latest.md",
    show_default=True,
    help="Path to write proof Markdown.",
)
@click.pass_context
def audit_proof(ctx: click.Context, out_json: str, out_md: str) -> None:
    """Run all guards and write proof artifacts to disk."""
    import json
    from datetime import datetime, timezone

    as_json: bool = ctx.obj.get("as_json", False)

    # Run guards inline (reuse logic from audit_guards).
    checks = [
        _run_script_guard(
            "validate_workflows",
            _SCRIPT_DIR / "validate_workflows.py",
        ),
        _run_shell_guard(
            "check_no_pyc",
            _SCRIPT_DIR / "check_no_pyc.sh",
        ),
        _run_script_guard(
            "check_source_keys",
            _SCRIPT_DIR / "check_source_keys.py",
            "--root", "backend/app",
            "--repo-root", ".",
        ),
        _run_script_guard(
            "check_statuses",
            _SCRIPT_DIR / "check_statuses.py",
            "--root", "backend/app",
        ),
        _run_compileall_guard(),
        _run_cli_availability_guard(),
    ]

    all_ok = all(c["ok"] for c in checks)
    errors = [c["detail"] for c in checks if not c["ok"]]
    timestamp = datetime.now(timezone.utc).isoformat()

    proof = {
        "ok": all_ok,
        "command": "audit.proof",
        "timestamp": timestamp,
        "checks": [{"name": c["name"], "ok": c["ok"]} for c in checks],
        "errors": errors,
    }

    # Write JSON proof.
    json_path = Path(out_json)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(json.dumps(proof, indent=2) + "\n")

    # Write Markdown proof.
    md_lines = [
        "# THE-JUDGE Proof Report",
        f"\n**Generated:** {timestamp}",
        f"\n**Status:** {'PASS' if all_ok else 'FAIL'}",
        "\n## Checks\n",
    ]
    for c in checks:
        status = "✓" if c["ok"] else "✗"
        md_lines.append(f"- {status} `{c['name']}`")
    if errors:
        md_lines.append("\n## Errors\n")
        for e in errors:
            md_lines.append(f"- {e}")

    md_path = Path(out_md)
    md_path.parent.mkdir(parents=True, exist_ok=True)
    md_path.write_text("\n".join(md_lines) + "\n")

    emit(
        {
            "ok": all_ok,
            "json_path": str(json_path),
            "md_path": str(md_path),
            "checks": [{"name": c["name"], "ok": c["ok"]} for c in checks],
            "errors": errors,
        },
        ok=all_ok,
        command="audit.proof",
        as_json=as_json,
    )
    if not all_ok:
        raise SystemExit(1)
