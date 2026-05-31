#!/usr/bin/env python3
"""Safe demo database reset helper.

This script intentionally refuses to delete non-demo database paths unless an
explicit override and path confirmation are provided.
"""

from __future__ import annotations

import os
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _path_from_sqlite_url(database_url: str) -> Path:
    if not database_url.startswith("sqlite:///"):
        raise ValueError("only supports sqlite")

    raw_path = database_url.removeprefix("sqlite:///")
    raw_db_path = Path(raw_path).expanduser()
    if not raw_db_path.is_absolute():
        raw_db_path = (Path.cwd() / raw_db_path).resolve(strict=False)
    db_path = raw_db_path.resolve(strict=False)

    demo_root = (REPO_ROOT / "demo").resolve(strict=False)
    allow_external = os.getenv("JTA_DEMO_ALLOW_DB_DELETE") == "1"
    confirm_path = os.getenv("JTA_DEMO_CONFIRM_PATH")

    try:
        is_inside_demo = raw_db_path.is_relative_to(demo_root)
    except AttributeError:
        # Python <3.9 fallback
        is_inside_demo = str(raw_db_path).startswith(str(demo_root) + os.sep)

    # Never allow a demo path symlink to escape without explicit override.
    if is_inside_demo and raw_db_path.exists() and raw_db_path.is_symlink():
        link_target = raw_db_path.resolve()
        try:
            target_inside_demo = link_target.is_relative_to(demo_root)
        except AttributeError:
            target_inside_demo = str(link_target).startswith(str(demo_root) + os.sep)
        if not target_inside_demo and not allow_external:
            raise ValueError("symlink resolves outside demo root")

    if is_inside_demo:
        return db_path

    if not allow_external:
        raise ValueError("refusing to delete non-demo sqlite path")

    if not confirm_path:
        raise ValueError("JTA_DEMO_CONFIRM_PATH is required for non-demo override")

    if Path(confirm_path).expanduser().resolve(strict=False) != db_path:
        raise ValueError("JTA_DEMO_CONFIRM_PATH must exactly match resolved sqlite path")

    return db_path


def main() -> int:
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
