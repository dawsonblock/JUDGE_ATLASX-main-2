from __future__ import annotations

from pathlib import Path


_ALLOWED_PATH_SUFFIXES = {
    "backend/app/audit/append_log.py",
    "backend/app/models/entities.py",
}


def test_no_direct_auditlog_insert_outside_append_log() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    app_root = repo_root / "backend" / "app"

    violations: list[str] = []
    for path in app_root.rglob("*.py"):
        rel = path.relative_to(repo_root).as_posix()
        if rel.startswith("backend/app/tests/"):
            continue
        if rel in _ALLOWED_PATH_SUFFIXES:
            continue

        for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "AuditLog(" not in line:
                continue
            violations.append(f"{rel}:{idx}")

    assert not violations, (
        "Direct AuditLog writes outside append_log are not allowed. "
        f"Violations: {violations}"
    )
