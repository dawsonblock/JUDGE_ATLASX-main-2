#!/usr/bin/env python3
"""Validate Alembic migration topology and upgrade path."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


def _run(
    cmd: list[str],
    cwd: Path,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    return subprocess.run(
        cmd,
        cwd=cwd,
        env=merged_env,
        capture_output=True,
        text=True,
        check=False,
    )


def main() -> int:
    backend_root = Path(__file__).resolve().parents[1]

    heads = _run([sys.executable, "-m", "alembic", "heads"], cwd=backend_root)
    if heads.returncode != 0:
        print("MIGRATIONS: FAIL alembic_heads_command")
        print(heads.stdout)
        print(heads.stderr)
        return 1

    head_count = heads.stdout.count("(head)")
    if head_count != 1:
        print(f"MIGRATIONS: FAIL head_count={head_count}")
        print(heads.stdout)
        return 1

    with tempfile.TemporaryDirectory(prefix="judge_migration_") as tmp:
        db_path = Path(tmp) / "migration_check.db"
        db_url = f"sqlite:///{db_path}"
        upgrade = _run(
            [sys.executable, "-m", "alembic", "upgrade", "head"],
            cwd=backend_root,
            env={"JTA_DATABASE_URL": db_url},
        )
        if upgrade.returncode != 0:
            print("MIGRATIONS: FAIL alembic_upgrade_head")
            print(upgrade.stdout)
            print(upgrade.stderr)
            return 1

    print("MIGRATIONS: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
