"""Tests for check_no_direct_ingestion_network_clients.py guard script.

Verifies that the script:
  1. Exits 0 on a clean repository (no violations).
  2. Exits 1 when a source adapter directly imports an HTTP client library.
  3. Exits 0 when a module in the ingestion tree declares NOT_RUNTIME = True
     (the module is allowlisted and skipped by Check 3).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent.parent  # backend/
_SCRIPT = _REPO_ROOT / "scripts" / "check_no_direct_ingestion_network_clients.py"
_ADAPTERS_DIR = _REPO_ROOT / "app" / "ingestion" / "source_adapters"


def _run_script(cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(_SCRIPT)],
        capture_output=True,
        text=True,
        cwd=str(cwd or _REPO_ROOT),
    )


def test_check_script_passes_on_clean_repository() -> None:
    """The guard script must exit 0 on the current (clean) repository state."""
    result = _run_script()
    assert result.returncode == 0, (
        f"check_no_direct_ingestion_network_clients.py found violations:\n"
        f"{result.stdout}\n{result.stderr}"
    )


def test_check_script_fails_on_forbidden_import_in_adapter(tmp_path: "pytest.TempdirFactory") -> None:
    """Injecting a direct httpx import into source_adapters/ causes exit 1."""
    import shutil

    fake_adapter = tmp_path / "source_adapters" / "bad_adapter.py"
    fake_adapter.parent.mkdir(parents=True)
    fake_adapter.write_text(
        "import httpx\n\nclass BadAdapter:\n    pass\n", encoding="utf-8"
    )

    # Run the real script but point it at a patched directory by running a
    # minimal inline script that monkeypatches _ADAPTERS_DIR.
    injected_script = tmp_path / "run_check.py"
    injected_script.write_text(
        f"""\
import sys
sys.path.insert(0, {str(_REPO_ROOT)!r})
sys.path.insert(0, {str(_REPO_ROOT / 'scripts')!r})
import check_no_direct_ingestion_network_clients as m
from pathlib import Path
m._ADAPTERS_DIR = Path({str(fake_adapter.parent)!r})
sys.exit(m.main())
""",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(injected_script)],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT / "scripts"),
    )
    assert result.returncode == 1, (
        "Expected exit 1 when adapter imports httpx but got 0.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert "forbidden import" in result.stdout or "httpx" in result.stdout


def test_not_runtime_module_is_skipped_by_check3(tmp_path: "pytest.TempdirFactory") -> None:
    """A file declaring NOT_RUNTIME = True must not trigger a Check 3 violation."""
    import shutil

    # Build a minimal fake ingestion tree
    fake_ingestion = tmp_path / "app" / "ingestion"
    fake_ingestion.mkdir(parents=True)
    (fake_ingestion / "__init__.py").write_text("", encoding="utf-8")
    (fake_ingestion / "source_adapters").mkdir()

    not_runtime_mod = fake_ingestion / "admin_only.py"
    not_runtime_mod.write_text(
        "NOT_RUNTIME: bool = True\nimport httpx\n", encoding="utf-8"
    )

    injected_script = tmp_path / "run_check.py"
    injected_script.write_text(
        f"""\
import sys
sys.path.insert(0, {str(_REPO_ROOT)!r})
sys.path.insert(0, {str(_REPO_ROOT / 'scripts')!r})
import check_no_direct_ingestion_network_clients as m
from pathlib import Path
m._INGESTION_DIR = Path({str(fake_ingestion)!r})
m._ADAPTERS_DIR = Path({str(fake_ingestion / "source_adapters")!r})
m._APP_DIR = Path({str(tmp_path / "app")!r})
sys.exit(m.main())
""",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(injected_script)],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT / "scripts"),
    )
    assert result.returncode == 0, (
        "NOT_RUNTIME module was incorrectly flagged by Check 3.\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
