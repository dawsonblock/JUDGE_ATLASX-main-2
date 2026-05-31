from __future__ import annotations

import os
from typing import Any
import importlib

nox = importlib.import_module("nox")

# Prevent Python from writing stale .pyc bytecache files during CI runs.
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

nox.options.sessions = ["backend", "frontend", "truth"]


@nox.session(python="3.11")
def backend(session: Any) -> None:
    """Install backend and run compile, migration-head, and pytest checks."""
    session.chdir("backend")
    session.install("-e", ".[test]")
    session.run("python", "-m", "compileall", "-q", "app")
    session.run("alembic", "heads")
    session.run("python", "-m", "pytest", "-q")


@nox.session(python=False)
def frontend(session: Any) -> None:
    """Run frontend clean install, typecheck, and production build."""
    session.chdir("frontend")
    session.run("npm", "ci", external=True)
    session.run("npm", "run", "typecheck", external=True)
    session.run("npm", "run", "build", external=True)


@nox.session(python=False)
def truth(session: Any) -> None:
    """Run truth-first repository guards."""
    session.run(
        "python3", "scripts/check_truth_claims.py", "--root", ".", external=True
    )
    session.run("python3", "scripts/validate_workflows.py", external=True)
    session.run("python3", "scripts/check_source_keys.py", external=True)
    session.run("python3", "scripts/check_statuses.py", external=True)


@nox.session(python=False)
def proof(session: Any) -> None:
    """Run the full-stack proof script."""
    session.run("bash", "scripts/proof_full_stack.sh", external=True)


@nox.session(python=False)
def enforcement(session: Any) -> None:
    """Run all mechanical enforcement guards and produce dated proof artifacts."""
    session.run("bash", "scripts/run_enforcement_proof.sh", external=True)
