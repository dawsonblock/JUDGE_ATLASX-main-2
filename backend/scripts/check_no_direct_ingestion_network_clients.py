#!/usr/bin/env python3
"""AST guard: assert no source adapter imports a direct HTTP client library.

Every outbound HTTP call from ingestion adapters must route through
``app.ingestion.fetcher.fetch_for_ingestion`` (which in turn calls
``app.security.safe_fetch.safe_fetch``).  Direct use of ``httpx``,
``requests``, ``aiohttp``, or ``urllib.request`` in adapter source files
bypasses SSRF protection and is therefore forbidden.

This script also checks for **experimental cross-imports**: production runtime
modules (anything under ``app/`` that is not a test and not inside an
experimental directory) may not import from the experimental packages
``app.ingestion.crime_sources`` or ``app.ingestion.laws``.  The only
authorised callers of those packages are listed in ``_EXPERIMENTAL_CALLERS``.

Usage::

    python scripts/check_no_direct_ingestion_network_clients.py

Exit code 0 = all clear.  Exit code 1 = violation(s) found.

``fetcher.py`` itself is allowlisted because it *is* the thin shim that
calls ``safe_fetch``; it is the only file permitted to import ``httpx``
indirectly via that call chain.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent
_ADAPTERS_DIR = _REPO_ROOT / "app" / "ingestion" / "source_adapters"
_APP_DIR = _REPO_ROOT / "app"
_INGESTION_DIR = _REPO_ROOT / "app" / "ingestion"

# Modules that must not appear as top-level imports in adapter files.
_FORBIDDEN_MODULES = frozenset(
    {
        "httpx",
        "requests",
        "aiohttp",
        "urllib.request",
        "http.client",
    }
)

# Files explicitly allowlisted for the HTTP-client check (by filename only).
_ALLOWLIST = frozenset({"fetcher.py"})

# Files fully exempted from Check 3 (path-based allowlist with justification).
_CHECK3_EXPLICIT_ALLOWLIST: frozenset[Path] = frozenset(
    {
        # web_monitor/crawlee_runner.py uses urllib.request *only* for robots.txt
        # safety checks via RobotFileParser.  This is a narrow approved exception;
        # it does not perform general outbound HTTP fetches.
        _REPO_ROOT / "app" / "ingestion" / "web_monitor" / "crawlee_runner.py",
    }
)

# Experimental package prefixes (dotted module paths).
# Files inside these directories are not subject to the cross-import check;
# only calls FROM production code TO these prefixes are flagged.
_EXPERIMENTAL_PREFIXES = frozenset(
    {
        "app.ingestion.crime_sources",
        "app.ingestion.laws",
    }
)

# Production (non-test) files that are explicitly permitted to import from
# experimental packages because they are the narrow, gated entry-points.
# To add a new authorised caller, put its path relative to _REPO_ROOT here
# and document why the exception is warranted.
_EXPERIMENTAL_CALLERS: frozenset[Path] = frozenset(
    {
        # Manual CSV/JSON upload endpoint gated by JTA_ENABLE_ADMIN_IMPORTS.
        _REPO_ROOT / "app" / "api" / "routes" / "admin_ingest.py",
        # Legacy U.S. ingestion routes gated by JTA_ENABLE_LEGACY_US_INGEST_ROUTES.
        _REPO_ROOT / "app" / "api" / "routes" / "admin_legacy_ingest.py",
        # Manual crime-incident CSV import and CourtListener trigger endpoint,
        # both gated by require_admin_imports (same JTA_ENABLE_ADMIN_IMPORTS flag).
        _REPO_ROOT / "app" / "api" / "routes" / "ingestion.py",
        # Phase 4 production adapter uses parser/validator helpers from
        # app.ingestion.laws.justice_canada but performs all network access via
        # fetch_for_ingestion.
        _REPO_ROOT / "app" / "ingestion" / "source_adapters" / "laws_justice_xml.py",
    }
)


def _check_file(path: Path) -> list[str]:
    """Return a list of violation strings found in *path*."""
    violations: list[str] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        violations.append(f"{path}: SyntaxError: {exc}")
        return violations

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".")[0]
                if alias.name in _FORBIDDEN_MODULES or top in _FORBIDDEN_MODULES:
                    violations.append(
                        f"{path}:{node.lineno}: forbidden import '{alias.name}'"
                    )
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            top = module.split(".")[0]
            if module in _FORBIDDEN_MODULES or top in _FORBIDDEN_MODULES:
                violations.append(
                    f"{path}:{node.lineno}: forbidden 'from {module} import ...'"
                )
    return violations


def _is_experimental_path(path: Path) -> bool:
    """Return True if *path* lives inside an experimental package directory."""
    try:
        rel = path.relative_to(_APP_DIR)
    except ValueError:
        return False
    parts = rel.parts
    # e.g. ("ingestion", "crime_sources", "foo.py") → prefix "app.ingestion.crime_sources"
    if len(parts) >= 2:
        dotted = "app." + ".".join(parts[:-1])
        for prefix in _EXPERIMENTAL_PREFIXES:
            if dotted == prefix or dotted.startswith(prefix + "."):
                return True
    return False


def _has_module_level_not_runtime(path: Path) -> bool:
    """Return True if *path* declares ``NOT_RUNTIME = True`` at module level."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (SyntaxError, OSError):
        return False
    for node in tree.body:  # only top-level statements
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id == "NOT_RUNTIME"
                    and isinstance(node.value, ast.Constant)
                    and node.value.value is True
                ):
                    return True
        elif isinstance(node, ast.AnnAssign):
            if (
                isinstance(node.target, ast.Name)
                and node.target.id == "NOT_RUNTIME"
                and node.value is not None
                and isinstance(node.value, ast.Constant)
                and node.value.value is True
            ):
                return True
    return False


def _dir_not_runtime(dirpath: Path) -> bool:
    """Return True if *dirpath*'s ``__init__.py`` declares NOT_RUNTIME = True."""
    init = dirpath / "__init__.py"
    return init.exists() and _has_module_level_not_runtime(init)


def _check_experimental_cross_imports(path: Path) -> list[str]:
    """Return violations if *path* imports from an experimental package."""
    violations: list[str] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return violations  # SyntaxError already reported in the HTTP check.

    for node in ast.walk(tree):
        module = ""
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
        elif isinstance(node, ast.Import):
            for alias in node.names:
                for prefix in _EXPERIMENTAL_PREFIXES:
                    if alias.name == prefix or alias.name.startswith(prefix + "."):
                        violations.append(
                            f"{path}:{node.lineno}: "
                            f"runtime import from experimental package '{alias.name}'"
                        )
            continue
        if module:
            for prefix in _EXPERIMENTAL_PREFIXES:
                if module == prefix or module.startswith(prefix + "."):
                    violations.append(
                        f"{path}:{node.lineno}: "
                        f"runtime import from experimental package '{module}'"
                    )
    return violations


def main() -> int:
    # ── Check 1: direct HTTP client imports in source_adapters/ ─────────────
    adapter_files = sorted(_ADAPTERS_DIR.glob("*.py"))
    http_violations: list[str] = []

    for path in adapter_files:
        if path.name in _ALLOWLIST:
            continue
        http_violations.extend(_check_file(path))

    # ── Check 2: experimental cross-imports from production runtime code ─────
    # Scan all .py files under app/ that are not test files and not inside an
    # experimental directory themselves.
    xp_violations: list[str] = []
    for path in sorted(_APP_DIR.rglob("*.py")):
        try:
            rel = path.relative_to(_APP_DIR)
        except ValueError:
            rel = path
        rel_str = str(rel)
        # Skip test files — they are permitted to exercise experimental code.
        if "test" in rel_str or "__pycache__" in rel_str:
            continue
        # Skip files that live inside the experimental packages themselves.
        if _is_experimental_path(path):
            continue
        # Skip explicitly authorised callers.
        if path in _EXPERIMENTAL_CALLERS:
            continue
        xp_violations.extend(_check_experimental_cross_imports(path))

    # ── Check 3: direct HTTP client imports anywhere in ingestion tree ───────
    # Scan all .py files under app/ingestion/ excluding:
    #   • source_adapters/ (covered by Check 1)
    #   • fetcher.py (approved network authority)
    #   • files in dirs whose __init__.py declares NOT_RUNTIME = True
    #   • files that themselves declare NOT_RUNTIME = True
    #   • explicitly allowlisted narrowly-scoped files (crawlee_runner.py)
    ingestion_http_violations: list[str] = []
    for path in sorted(_INGESTION_DIR.rglob("*.py")):
        try:
            rel_str = str(path.relative_to(_APP_DIR))
        except ValueError:
            rel_str = str(path)
        if "__pycache__" in rel_str:
            continue
        if "test" in rel_str:
            continue
        if "source_adapters" in rel_str:
            continue  # covered by Check 1
        if path.name in _ALLOWLIST:
            continue  # fetcher.py
        if _dir_not_runtime(path.parent):
            continue  # whole package is NOT_RUNTIME
        if _has_module_level_not_runtime(path):
            continue  # module declares itself NOT_RUNTIME
        if path in _CHECK3_EXPLICIT_ALLOWLIST:
            continue  # narrow approved exception
        ingestion_http_violations.extend(_check_file(path))

    # ── Report ───────────────────────────────────────────────────────────────
    rc = 0

    if http_violations:
        print("ERROR: Direct network client imports found in ingestion adapters:")
        for v in http_violations:
            print(f"  {v}")
        print(
            "\nAll outbound HTTP calls must route through "
            "app.ingestion.fetcher.fetch_for_ingestion."
        )
        rc = 1
    else:
        print(
            f"OK: {len(adapter_files)} adapter file(s) checked — "
            "no direct network client imports found."
        )

    if xp_violations:
        print(
            "\nERROR: Runtime code imports from experimental packages "
            "(app.ingestion.crime_sources / app.ingestion.laws):"
        )
        for v in xp_violations:
            print(f"  {v}")
        print(
            "\nAdd an explicit entry to _EXPERIMENTAL_CALLERS in this script "
            "if the import is intentional and gated behind a feature flag."
        )
        rc = 1
    else:
        print(
            "OK: No unauthorised runtime imports from experimental packages found."
        )

    if ingestion_http_violations:
        print(
            "\nERROR: Direct network client imports found in ingestion tree "
            "(outside source_adapters/, fetcher.py, and NOT_RUNTIME modules):"
        )
        for v in ingestion_http_violations:
            print(f"  {v}")
        print(
            "\nAdd NOT_RUNTIME: bool = True to the module or its package __init__.py "
            "if it is experimental/admin-only, or migrate to "
            "app.ingestion.fetcher.fetch_for_ingestion()."
        )
        rc = 1
    else:
        print(
            "OK: Ingestion tree checked — no unauthorised direct network client "
            "imports found outside allowlisted modules."
        )

    return rc


if __name__ == "__main__":
    sys.exit(main())
