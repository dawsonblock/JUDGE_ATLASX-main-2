from __future__ import annotations

import re
from pathlib import Path

from app.auth.actor import VALID_ADMIN_ROLES
from app.security.permissions import MUTATION_PERMISSIONS, READ_PERMISSIONS

CANONICAL = set(VALID_ADMIN_ROLES)
ALLOWED_LEGACY_ALIASES = {"system_admin"}
ROLE_LITERAL = re.compile(r"\b(viewer|reviewer|source_admin|admin|owner|superadmin|legacy_admin|staff|moderator|system_admin)\b")


def test_permissions_role_sets_use_canonical_roles() -> None:
    for action, roles in {**MUTATION_PERMISSIONS, **READ_PERMISSIONS}.items():
        assert roles <= CANONICAL, (
            f"permission action '{action}' includes non-canonical roles: {sorted(roles - CANONICAL)}"
        )


def test_auth_security_runtime_files_do_not_use_stale_role_literals() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    scan_dirs = [repo_root / "backend" / "app" / "auth", repo_root / "backend" / "app" / "security"]

    violations: list[str] = []
    for scan_dir in scan_dirs:
        for path in scan_dir.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for line_no, line in enumerate(text.splitlines(), start=1):
                for match in ROLE_LITERAL.findall(line):
                    if match in CANONICAL or match in ALLOWED_LEGACY_ALIASES:
                        continue
                    violations.append(f"{path}:{line_no}: disallowed role literal '{match}'")

    assert not violations, "\n".join(violations)
