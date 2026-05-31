#!/usr/bin/env python3
"""Repository boundary guard: enforce runtime isolation rules.

Checks that code in JUDGE-main respects the boundaries documented in
``RUNTIME_BOUNDARIES.md`` and ``REPO_REALITY.md``:

1. **External-repo isolation** — modules inside ``external/`` or files that
   look like sub-repo checkouts must not be imported by backend runtime code.

2. **Experimental package isolation** — packages marked with ``NOT_RUNTIME``
   (currently ``app.ingestion.crime_sources`` and ``app.ingestion.laws``) must
   not be imported by general runtime code outside their allowlist.

3. **Sentinel presence** — every ``__init__.py`` inside a known-experimental
   directory must expose ``NOT_RUNTIME = True``.

Usage::

    python scripts/check_repo_boundaries.py

Exit code 0 = all clear.  Exit code 1 = violation(s) found.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Path anchors
# ---------------------------------------------------------------------------

_SCRIPT_DIR = Path(__file__).parent
_BACKEND_DIR = _SCRIPT_DIR.parent
_REPO_ROOT = _BACKEND_DIR.parent
_APP_DIR = _BACKEND_DIR / "app"

# ---------------------------------------------------------------------------
# Experimental packages that must carry NOT_RUNTIME = True in __init__.py
# and must not be imported from general runtime code.
# ---------------------------------------------------------------------------

_EXPERIMENTAL_DIRS: list[Path] = [
    _APP_DIR / "ingestion" / "crime_sources",
    _APP_DIR / "ingestion" / "laws",
]

# Packages whose __init__ must expose NOT_RUNTIME (dotted from backend root).
_EXPERIMENTAL_PREFIXES = frozenset(
    {
        "app.ingestion.crime_sources",
        "app.ingestion.laws",
    }
)

# Production runtime files explicitly authorised to import experimental code.
_EXPERIMENTAL_CALLERS_ALLOWLIST: frozenset[Path] = frozenset(
    {
        _APP_DIR / "api" / "routes" / "admin_ingest.py",
        # legacy U.S. routes — gated by JTA_ENABLE_LEGACY_US_INGEST_ROUTES
        _APP_DIR / "api" / "routes" / "admin_legacy_ingest.py",
        # admin CSV + courtlistener routes — gated by require_admin_imports
        _APP_DIR / "api" / "routes" / "ingestion.py",
    }
)

# ---------------------------------------------------------------------------
# Check 1: NOT_RUNTIME sentinel present in experimental __init__.py files
# ---------------------------------------------------------------------------


def check_not_runtime_sentinels() -> list[str]:
    """Return violations for experimental packages missing the NOT_RUNTIME sentinel."""
    violations: list[str] = []
    for pkg_dir in _EXPERIMENTAL_DIRS:
        init_path = pkg_dir / "__init__.py"
        if not init_path.exists():
            violations.append(
                f"{init_path}: missing __init__.py in experimental package"
            )
            continue
        try:
            tree = ast.parse(init_path.read_text(encoding="utf-8"), filename=str(init_path))
        except SyntaxError as exc:
            violations.append(f"{init_path}: SyntaxError: {exc}")
            continue

        found = False
        for node in ast.walk(tree):
            # Looking for: NOT_RUNTIME = True  (module-level assignment)
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id == "NOT_RUNTIME"
                and isinstance(node.value, ast.Constant)
                and node.value.value is True
            ):
                found = True
                break
            if (
                isinstance(node, ast.AnnAssign)
                and isinstance(node.target, ast.Name)
                and node.target.id == "NOT_RUNTIME"
                and node.value is not None
                and isinstance(node.value, ast.Constant)
                and node.value.value is True
            ):
                found = True
                break
        if not found:
            violations.append(
                f"{init_path}: experimental __init__.py missing "
                "'NOT_RUNTIME: bool = True' sentinel"
            )
    return violations


# ---------------------------------------------------------------------------
# Check 2: No unauthorised runtime cross-imports from experimental packages
# ---------------------------------------------------------------------------


def _is_in_experimental(path: Path) -> bool:
    for exp_dir in _EXPERIMENTAL_DIRS:
        try:
            path.relative_to(exp_dir)
            return True
        except ValueError:
            pass
    return False


def _check_file_for_experimental_imports(path: Path) -> list[str]:
    violations: list[str] = []
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, OSError):
        return violations

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for prefix in _EXPERIMENTAL_PREFIXES:
                if module == prefix or module.startswith(prefix + "."):
                    violations.append(
                        f"{path}:{node.lineno}: "
                        f"runtime import from experimental package '{module}'"
                    )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                for prefix in _EXPERIMENTAL_PREFIXES:
                    if alias.name == prefix or alias.name.startswith(prefix + "."):
                        violations.append(
                            f"{path}:{node.lineno}: "
                            f"runtime import from experimental package '{alias.name}'"
                        )
    return violations


def check_experimental_cross_imports() -> list[str]:
    violations: list[str] = []
    for path in sorted(_APP_DIR.rglob("*.py")):
        rel_str = str(path.relative_to(_BACKEND_DIR))
        # Skip test files and cache dirs.
        if "test" in rel_str or "__pycache__" in rel_str:
            continue
        # Skip files that live inside the experimental packages themselves.
        if _is_in_experimental(path):
            continue
        # Skip authorised callers.
        if path in _EXPERIMENTAL_CALLERS_ALLOWLIST:
            continue
        violations.extend(_check_file_for_experimental_imports(path))
    return violations


# ---------------------------------------------------------------------------
# Check 3: No backend Python files import from external/ sub-repos
# ---------------------------------------------------------------------------

_EXTERNAL_PACKAGE_NAMES: frozenset[str] = frozenset(
    {
        # CLI-Anything-main top-level packages
        "cli_anything",
        "cli_hub",
        # memvid sub-repo (Rust; Python bindings would be named memvid)
        "memvid",
    }
)


def _check_file_for_external_imports(path: Path) -> list[str]:
    violations: list[str] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, OSError):
        return violations

    for node in ast.walk(tree):
        names_to_check: list[str] = []
        if isinstance(node, ast.Import):
            names_to_check = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names_to_check = [node.module]

        for name in names_to_check:
            top = name.split(".")[0]
            if top in _EXTERNAL_PACKAGE_NAMES:
                violations.append(
                    f"{path}:{node.lineno}: "
                    f"import from external sub-repo package '{name}'"
                )
    return violations


def check_no_external_repo_imports() -> list[str]:
    violations: list[str] = []
    for path in sorted(_APP_DIR.rglob("*.py")):
        rel_str = str(path.relative_to(_BACKEND_DIR))
        if "__pycache__" in rel_str:
            continue
        violations.extend(_check_file_for_external_imports(path))
    return violations


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    rc = 0

    # -- Check 1 --
    sentinel_violations = check_not_runtime_sentinels()
    if sentinel_violations:
        print("ERROR: Experimental package(s) missing NOT_RUNTIME sentinel:")
        for v in sentinel_violations:
            print(f"  {v}")
        rc = 1
    else:
        print(
            f"OK: {len(_EXPERIMENTAL_DIRS)} experimental package(s) have "
            "NOT_RUNTIME sentinel."
        )

    # -- Check 2 --
    xp_violations = check_experimental_cross_imports()
    if xp_violations:
        print(
            "\nERROR: Unauthorised runtime imports from experimental packages:"
        )
        for v in xp_violations:
            print(f"  {v}")
        print(
            "\nAdd an explicit entry to _EXPERIMENTAL_CALLERS_ALLOWLIST in "
            "this script if the import is intentional and gated behind a "
            "feature flag."
        )
        rc = 1
    else:
        print(
            "OK: No unauthorised runtime imports from experimental packages."
        )

    # -- Check 3 --
    ext_violations = check_no_external_repo_imports()
    if ext_violations:
        print(
            "\nERROR: Backend code imports from external sub-repo packages:"
        )
        for v in ext_violations:
            print(f"  {v}")
        print(
            "\nExternal repositories in external/ are reference material only. "
            "Do not import or vendor them into the JUDGE runtime."
        )
        rc = 1
    else:
        print("OK: No imports from external sub-repo packages found.")

    return rc


if __name__ == "__main__":
    sys.exit(main())
