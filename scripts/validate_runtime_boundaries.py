#!/usr/bin/env python3
"""Validate runtime boundaries for alpha release safety.

Fails when runtime code references archived or reference-only materials, when
container configs are unsafe, or when source governance claims unsupported
machine ingestion.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

FORBIDDEN_IMPORT_PREFIXES = (
    "external_reference",
    "legacy_disabled",
    "archived_research",
    "reference_only",
)

IGNORED_SCAN_DIRS = {
    "node_modules",
    ".next",
    "dist",
    "coverage",
    "__pycache__",
    ".pytest_cache",
    ".venv",
    "venv",
}

FORBIDDEN_PROOF_PATH_MARKERS = (
    "external_reference",
    "artifacts/old",
    "artifacts/archive",
    "generated_logs",
    "tmp",
    "cache",
)

_STRICT_CACHE_SEGMENTS = {
    "cache",
    ".cache",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
}

_MANIFEST_EXCLUSION_FIELDS = {
    "excluded_directories",
    "excluded_paths",
    "excluded_path_markers",
}

DANGEROUS_PROD_FLAGS = {
    "JTA_ENABLE_LEGACY_ADMIN_TOKEN": "true",
    "JTA_ENABLE_ADMIN_IMPORTS": "true",
}


def _scan_python_imports(base: Path) -> list[str]:
    violations: list[str] = []
    py_files = [
        p
        for p in base.rglob("*.py")
        if p.is_file() and not any(part in IGNORED_SCAN_DIRS for part in p.parts)
    ]
    pattern = re.compile(r"^\s*(?:from|import)\s+([a-zA-Z0-9_\.]+)")

    for path in py_files:
        rel = path.relative_to(REPO_ROOT)
        text = path.read_text(encoding="utf-8", errors="ignore")
        for idx, line in enumerate(text.splitlines(), start=1):
            m = pattern.match(line)
            if not m:
                continue
            module = m.group(1)
            if module.startswith(FORBIDDEN_IMPORT_PREFIXES):
                violations.append(f"{rel}:{idx}: forbidden import '{module}'")
    return violations


def _scan_frontend_imports(base: Path) -> list[str]:
    violations: list[str] = []
    patterns = ("*.ts", "*.tsx", "*.js", "*.jsx", "*.mjs", "*.cjs")
    import_re = re.compile(r"from\s+[\"']([^\"']+)[\"']")
    require_re = re.compile(r"require\(\s*[\"']([^\"']+)[\"']\s*\)")

    files: list[Path] = []
    for pat in patterns:
        files.extend(
            p
            for p in base.rglob(pat)
            if p.is_file() and not any(part in IGNORED_SCAN_DIRS for part in p.parts)
        )

    for path in files:
        rel = path.relative_to(REPO_ROOT)
        text = path.read_text(encoding="utf-8", errors="ignore")
        for idx, line in enumerate(text.splitlines(), start=1):
            matches = import_re.findall(line) + require_re.findall(line)
            for value in matches:
                if _contains_forbidden_import_segment(value):
                    violations.append(f"{rel}:{idx}: forbidden import '{value}'")
    return violations


def _normalized_path_parts(value: str) -> tuple[str, ...]:
    normalized = value.replace("\\", "/")
    return tuple(part for part in normalized.split("/") if part and part != ".")


def _contains_forbidden_import_segment(value: str) -> bool:
    parts = _normalized_path_parts(value)
    return any(part in FORBIDDEN_IMPORT_PREFIXES for part in parts)


def _matches_marker(value: str, marker: str) -> bool:
    parts = _normalized_path_parts(value)
    if not parts:
        return False

    if marker == "cache":
        return any(part in _STRICT_CACHE_SEGMENTS for part in parts)

    if "/" in marker:
        marker_parts = tuple(part for part in marker.split("/") if part)
        if len(parts) < len(marker_parts):
            return False
        for idx in range(len(parts) - len(marker_parts) + 1):
            if parts[idx : idx + len(marker_parts)] == marker_parts:
                return True
        return False

    return marker in parts


def _docker_context_violations() -> list[str]:
    violations: list[str] = []

    compose = REPO_ROOT / "docker-compose.yml"
    if compose.exists():
        text = compose.read_text(encoding="utf-8", errors="ignore")
        contexts = re.findall(r"^\s*context:\s*(\S+)", text, flags=re.MULTILINE)
        if "." in contexts:
            dockerignore = REPO_ROOT / ".dockerignore"
            dockerignore_text = dockerignore.read_text(encoding="utf-8", errors="ignore") if dockerignore.exists() else ""
            if "external_reference" not in dockerignore_text:
                violations.append(
                    "docker-compose.yml uses context '.' but .dockerignore does not exclude external_reference"
                )

    for path in REPO_ROOT.glob("Dockerfile*"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        for idx, line in enumerate(text.splitlines(), start=1):
            low = line.lower()
            if ("copy" in low or "add" in low) and "external_reference" in low:
                violations.append(f"{path.relative_to(REPO_ROOT)}:{idx}: dockerfile references external_reference")

    return violations


def _proof_manifest_violations() -> list[str]:
    violations: list[str] = []
    manifests = [
        REPO_ROOT / "artifacts" / "current" / "PROOF_MANIFEST.json",
        REPO_ROOT / "artifacts" / "proof" / "current" / "proof_manifest.json",
    ]

    def _contains_forbidden(obj: Any, marker: str, current_key: str | None = None) -> bool:
        if isinstance(obj, dict):
            return any(
                _contains_forbidden(v, marker, k)
                for k, v in obj.items()
            )
        if isinstance(obj, list):
            if current_key in _MANIFEST_EXCLUSION_FIELDS:
                return False
            return any(_contains_forbidden(v, marker, current_key) for v in obj)
        if isinstance(obj, str):
            if current_key in _MANIFEST_EXCLUSION_FIELDS:
                return False
            return _matches_marker(obj, marker)
        return False

    for manifest in manifests:
        if not manifest.exists():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            violations.append(f"{manifest.relative_to(REPO_ROOT)} is invalid JSON")
            continue
        for marker in FORBIDDEN_PROOF_PATH_MARKERS:
            if _contains_forbidden(data, marker):
                violations.append(
                    f"{manifest.relative_to(REPO_ROOT)} references excluded path marker '{marker}'"
                )
    return violations


def _source_registry_violations() -> list[str]:
    violations: list[str] = []
    try:
        import yaml  # type: ignore
        from app.ingestion.source_adapters import ADAPTER_REGISTRY
    except Exception as exc:  # noqa: BLE001
        return [f"cannot import source registry dependencies: {exc}"]

    yaml_path = REPO_ROOT / "backend" / "app" / "ingestion" / "sources" / "canada_saskatchewan_sources.yaml"
    if not yaml_path.exists():
        return ["missing source registry yaml: backend/app/ingestion/sources/canada_saskatchewan_sources.yaml"]

    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
    for source in data.get("sources", []):
        source_key = str(source.get("source_key") or "unknown")
        source_class = source.get("source_class")
        parser = source.get("parser")
        auto_status = source.get("automation_status")

        if source_class == "machine_ingest":
            if not parser:
                violations.append(f"{source_key}: machine_ingest missing parser")
                continue
            if parser not in ADAPTER_REGISTRY:
                violations.append(
                    f"{source_key}: machine_ingest parser '{parser}' has no registered adapter"
                )
            if auto_status in {"machine_ready_enabled", "machine_ready_disabled"} and parser not in ADAPTER_REGISTRY:
                violations.append(
                    f"{source_key}: automation_status={auto_status} but parser adapter is missing"
                )
    return violations


def _production_config_violations() -> list[str]:
    violations: list[str] = []
    prod_env = REPO_ROOT / ".env.example.production"
    if not prod_env.exists():
        return violations

    text = prod_env.read_text(encoding="utf-8", errors="ignore")
    for key, expected_true in DANGEROUS_PROD_FLAGS.items():
        pattern = re.compile(rf"^\s*{re.escape(key)}\s*=\s*(\S+)\s*$", re.MULTILINE)
        m = pattern.search(text)
        if m and m.group(1).strip().lower() == expected_true:
            violations.append(f".env.example.production enables unsafe flag {key}=true")

    if re.search(r"^\s*JTA_CORS_ORIGINS\s*=\s*\*\s*$", text, flags=re.MULTILINE):
        violations.append(".env.example.production sets JTA_CORS_ORIGINS=*")

    return violations


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--static-only",
        action="store_true",
        default=False,
        help=(
            "Run only dependency-free static checks (import scan, docker context, "
            "manifest validation, production config). Skips source registry check "
            "which requires backend dependencies to be installed."
        ),
    )
    args = parser.parse_args(argv if argv is not None else [])

    violations: list[str] = []

    violations.extend(_scan_python_imports(REPO_ROOT / "backend" / "app"))
    violations.extend(_scan_frontend_imports(REPO_ROOT / "frontend"))
    violations.extend(_docker_context_violations())
    violations.extend(_proof_manifest_violations())
    violations.extend(_production_config_violations())

    if args.static_only:
        print("[static-only] skipping source registry check (requires backend install)")
    else:
        violations.extend(_source_registry_violations())

    if violations:
        print("runtime boundary validation: FAIL")
        for v in violations:
            print(f" - {v}")
        return 1

    print("runtime boundary validation: PASS")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
