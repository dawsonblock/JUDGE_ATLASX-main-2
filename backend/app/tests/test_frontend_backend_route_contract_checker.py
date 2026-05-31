from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[3]
    / "scripts"
    / "check_frontend_backend_route_contract.py"
)


def _load_module():
    spec = importlib.util.spec_from_file_location(
        "check_frontend_backend_route_contract", SCRIPT_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _patch_module_paths(module, monkeypatch, repo_root: Path) -> None:
    monkeypatch.setattr(module, "REPO_ROOT", repo_root)
    monkeypatch.setattr(module, "FRONTEND_ROOT", repo_root / "frontend")
    monkeypatch.setattr(
        module,
        "BACKEND_ROUTES_ROOT",
        repo_root / "backend" / "app" / "api" / "routes",
    )
    monkeypatch.setattr(
        module,
        "ALLOWLIST_PATH",
        repo_root / "scripts" / "route_contract_allowlist.json",
    )


def test_extract_frontend_calls_ignores_import_alias_substring(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = _load_module()
    repo_root = tmp_path / "repo"
    _patch_module_paths(module, monkeypatch, repo_root)

    _write(
        repo_root / "frontend" / "app" / "admin" / "status" / "page.tsx",
        "\n".join(
            [
                'import { fetchAlphaReadinessStatus } '
                'from "@/lib/api/status";',
                'const endpoint = "/api/status/alpha-readiness";',
            ]
        )
        + "\n",
    )

    calls = module._extract_frontend_api_calls()

    assert "/api/status/alpha-readiness" in calls
    assert "/api/status" not in calls


def test_main_passes_without_false_unresolved_alias_path(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    module = _load_module()
    repo_root = tmp_path / "repo"
    _patch_module_paths(module, monkeypatch, repo_root)

    _write(
        repo_root / "scripts" / "route_contract_allowlist.json",
        json.dumps([], indent=2) + "\n",
    )

    _write(
        repo_root / "frontend" / "app" / "admin" / "status" / "page.tsx",
        "\n".join(
            [
                'import { fetchAlphaReadinessStatus } '
                'from "@/lib/api/status";',
                'const endpoint = "/api/status/alpha-readiness";',
            ]
        )
        + "\n",
    )

    _write(
        repo_root / "backend" / "app" / "api" / "routes" / "status.py",
        "\n".join(
            [
                "from fastapi import APIRouter",
                "",
                'router = APIRouter(prefix="/api/status")',
                "",
                '@router.get("/alpha-readiness")',
                "def alpha_readiness():",
                "    return {}",
            ]
        )
        + "\n",
    )

    rc = module.main()
    output = capsys.readouterr().out

    assert rc == 0
    assert "RESULT: PASS" in output
    assert "Unresolved frontend API paths:" not in output
