#!/usr/bin/env python3
"""Validate configuration contract consistency across code, env examples, and docs."""

from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path


BACKEND_CONTRACT_VARS = [
    "JTA_APP_ENV",
    "JTA_RUNTIME_PROFILE",
    "JTA_DATABASE_URL",
    "JTA_REDIS_URL",
    "JTA_JWT_SECRET_KEY",
    "JTA_JWT_ALGORITHM",
    "JTA_CORS_ORIGINS",
    "JTA_EVIDENCE_STORE_ROOT",
    "JTA_EVIDENCE_STORE_REQUIRED",
    "JTA_STORAGE_BACKEND",
    "JTA_ENABLE_EXPERIMENTAL_LIVE_MAP",
    "JTA_ENABLE_WORKFLOW_ADMIN",
    "JTA_ENABLE_LEGACY_ADMIN_TOKEN",
    "JTA_FETCH_EGRESS_PROXY",
    "JTA_RATE_LIMIT_BACKEND",
    "JTA_INGESTION_QUEUE_BACKEND",
]

FRONTEND_CONTRACT_VARS = [
    "NEXT_PUBLIC_API_BASE_URL",
    "NEXT_PUBLIC_ENABLE_LIVE_MAP",
    "NEXT_PUBLIC_ENABLE_ADMIN_UI",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _extract_env_keys(text: str) -> set[str]:
    return set(re.findall(r"\b([A-Z][A-Z0-9_]+)\s*=", text))


def _extract_settings_fields(config_path: Path) -> set[str]:
    tree = ast.parse(_read(config_path), filename=str(config_path))
    fields: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "Settings":
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    fields.add(stmt.target.id)
                if isinstance(stmt, ast.Assign):
                    for tgt in stmt.targets:
                        if isinstance(tgt, ast.Name):
                            fields.add(tgt.id)
    return fields


def _to_field_name(var_name: str) -> str:
    return var_name.removeprefix("JTA_").lower()


def verify(root: Path) -> list[str]:
    errors: list[str] = []
    allowed_non_settings = {
        "JTA_FETCH_EGRESS_PROXY",  # enforced via startup env checks
    }

    config_path = root / "backend/app/core/config.py"
    root_env_example = root / ".env.example"
    backend_env_example = root / "backend/.env.example"
    frontend_env_example = root / "frontend/.env.example"
    setup_doc = root / "docs/setup/MACOS_VSCODE_ALPHA_SETUP.md"
    deploy_doc = root / "docs/deployment/ALPHA_DEPLOYMENT.md"

    required_files = [
        config_path,
        root_env_example,
        backend_env_example,
        frontend_env_example,
        setup_doc,
        deploy_doc,
    ]

    for file_path in required_files:
        if not file_path.exists():
            errors.append(f"missing_required_file:{file_path.relative_to(root).as_posix()}")
    if errors:
        return errors

    settings_fields = _extract_settings_fields(config_path)

    # 1) Setting exists in code but not documented (for contract set).
    for var_name in BACKEND_CONTRACT_VARS:
        if var_name in allowed_non_settings:
            continue
        field_name = _to_field_name(var_name)
        if field_name not in settings_fields:
            errors.append(f"contract_var_not_in_code:{var_name}:expected_field={field_name}")

    files_to_check = {
        ".env.example": _read(root_env_example),
        "backend/.env.example": _read(backend_env_example),
        "frontend/.env.example": _read(frontend_env_example),
        "docs/setup/MACOS_VSCODE_ALPHA_SETUP.md": _read(setup_doc),
        "docs/deployment/ALPHA_DEPLOYMENT.md": _read(deploy_doc),
    }

    for var_name in BACKEND_CONTRACT_VARS:
        for file_name in (
            ".env.example",
            "backend/.env.example",
            "docs/setup/MACOS_VSCODE_ALPHA_SETUP.md",
            "docs/deployment/ALPHA_DEPLOYMENT.md",
        ):
            if var_name not in files_to_check[file_name]:
                errors.append(f"undocumented_or_missing:{var_name}:file={file_name}")

    for var_name in FRONTEND_CONTRACT_VARS:
        for file_name in (
            ".env.example",
            "frontend/.env.example",
            "docs/setup/MACOS_VSCODE_ALPHA_SETUP.md",
        ):
            if var_name not in files_to_check[file_name]:
                errors.append(f"undocumented_or_missing:{var_name}:file={file_name}")

    # 2) Documented setting no longer exists in code (for JTA_ vars in setup/deploy docs).
    documented_jta_vars = set()
    documented_jta_vars.update(re.findall(r"\b(JTA_[A-Z0-9_]+)\b", files_to_check["docs/setup/MACOS_VSCODE_ALPHA_SETUP.md"]))
    documented_jta_vars.update(re.findall(r"\b(JTA_[A-Z0-9_]+)\b", files_to_check["docs/deployment/ALPHA_DEPLOYMENT.md"]))
    for var_name in sorted(documented_jta_vars):
        field_name = _to_field_name(var_name)
        if field_name not in settings_fields and var_name not in allowed_non_settings:
            errors.append(f"documented_setting_missing_in_code:{var_name}")

    # 3) Production-dangerous defaults in deployment docs.
    deploy_text = files_to_check["docs/deployment/ALPHA_DEPLOYMENT.md"]
    dangerous_patterns = [
        "JTA_APP_ENV=development",
        "JTA_ENABLE_EXPERIMENTAL_LIVE_MAP=true",
        "JTA_ENABLE_WORKFLOW_ADMIN=true",
        "JTA_ENABLE_LEGACY_ADMIN_TOKEN=true",
        "JTA_CORS_ORIGINS=*",
    ]
    for pattern in dangerous_patterns:
        if pattern in deploy_text:
            errors.append(f"dangerous_deployment_default:{pattern}")

    # 4) Experimental features must include warnings in docs.
    if "JTA_ENABLE_EXPERIMENTAL_LIVE_MAP" in deploy_text:
        low = deploy_text.lower()
        if "experimental" not in low or "not production" not in low:
            errors.append("experimental_feature_missing_warning:ALPHA_DEPLOYMENT")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    errors = verify(root)
    if errors:
        print("CONFIG DOCS CONSISTENCY: FAIL")
        for err in errors:
            print(f"- {err}")
        return 1

    print("CONFIG DOCS CONSISTENCY: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
