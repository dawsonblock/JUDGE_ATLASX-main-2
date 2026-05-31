#!/usr/bin/env python3
"""Validate the Node runtime against the declared frontend policy."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8").strip()


def _parse_version(version: str) -> tuple[int, int, int] | None:
    match = re.match(r"^v?(\d+)(?:\.(\d+))?(?:\.(\d+))?", version.strip())
    if not match:
        return None
    return (
        int(match.group(1)),
        int(match.group(2) or 0),
        int(match.group(3) or 0),
    )


def _major_from_policy(value: str | None) -> int | None:
    if not value:
        return None
    parsed = _parse_version(value)
    if parsed is None:
        return None
    return parsed[0]


def _compare_versions(left: tuple[int, int, int], right: tuple[int, int, int]) -> int:
    if left < right:
        return -1
    if left > right:
        return 1
    return 0


def _satisfies_range(version: str, spec: str) -> bool:
    parsed_version = _parse_version(version)
    if parsed_version is None:
        return False

    comparators = [token for token in spec.split() if token]
    for comparator in comparators:
        if comparator.startswith(">="):
            target = _parse_version(comparator[2:])
            if target is None or _compare_versions(parsed_version, target) < 0:
                return False
        elif comparator.startswith(">"):
            target = _parse_version(comparator[1:])
            if target is None or _compare_versions(parsed_version, target) <= 0:
                return False
        elif comparator.startswith("<="):
            target = _parse_version(comparator[2:])
            if target is None or _compare_versions(parsed_version, target) > 0:
                return False
        elif comparator.startswith("<"):
            target = _parse_version(comparator[1:])
            if target is None or _compare_versions(parsed_version, target) >= 0:
                return False
        else:
            target = _parse_version(comparator)
            if target is None or parsed_version != target:
                return False
    return True


def _run_version_command(command: list[str]) -> str:
    proc = subprocess.run(command, capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"command failed: {' '.join(command)}")
    return proc.stdout.strip()


def _resolve_runtime_versions(
    required_selector: str,
    required_major: int,
    node_range: str | None,
) -> tuple[str, str, str]:
    """Resolve node/npm versions, preferring policy-compliant runtime.

    Uses the current shell runtime first. If it does not satisfy the declared
    major/range and nvm is available, it attempts ``nvm use <required_major>``
    and returns that runtime instead.
    """
    node_version = _run_version_command(["node", "--version"])
    npm_version = _run_version_command(["npm", "--version"])

    parsed = _parse_version(node_version)
    major_ok = parsed is not None and parsed[0] == required_major
    range_ok = isinstance(node_range, str) and _satisfies_range(node_version, node_range)
    if major_ok and range_ok:
        return node_version, npm_version, "shell"

    nvm_dir = os.environ.get("NVM_DIR", str(Path.home() / ".nvm"))
    nvm_sh = Path(nvm_dir) / "nvm.sh"
    if not nvm_sh.exists():
        return node_version, npm_version, "shell"

    cmd = (
        f'NVM_DIR="{nvm_dir}"; '
        f'[ -s "{nvm_sh}" ] && . "{nvm_sh}"; '
        f'nvm use {required_selector} >/dev/null 2>&1 && node --version && npm --version'
    )
    proc = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        return node_version, npm_version, "shell"

    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if len(lines) < 2:
        return node_version, npm_version, "shell"
    return lines[-2], lines[-1], "nvm"


def _validate_node_value(
    label: str,
    value: str | None,
    nvmrc_major: str,
    node_range: str | None,
    runtime_node_version: str,
) -> list[str]:
    errors: list[str] = []
    if not value or value == "unknown":
        return [f"{label}: missing stored node_version"]

    parsed_value = _parse_version(value)
    if parsed_value is None:
        return [f"{label}: unable to parse stored node_version '{value}'"]

    declared_major = _major_from_policy(nvmrc_major)
    if declared_major is None:
        return [f"{label}: unable to parse .nvmrc value '{nvmrc_major}'"]
    if parsed_value[0] != declared_major:
        errors.append(
            f"{label}: stored node_version '{value}' disagrees with .nvmrc major={nvmrc_major}"
        )
    if not isinstance(node_range, str) or not _satisfies_range(value, node_range):
        errors.append(
            f"{label}: stored node_version '{value}' does not satisfy engines.node '{node_range}'"
        )

    runtime_parsed = _parse_version(runtime_node_version)
    if runtime_parsed is not None and parsed_value != runtime_parsed:
        errors.append(
            f"{label}: stored node_version '{value}' does not match runtime {runtime_node_version}"
        )
    return errors


def _validate_npm_value(
    label: str,
    value: str | None,
    npm_range: str | None,
    runtime_npm_version: str,
) -> list[str]:
    errors: list[str] = []
    if not value or value == "unknown":
        return [f"{label}: missing stored npm_version"]

    parsed_value = _parse_version(value)
    if parsed_value is None:
        return [f"{label}: unable to parse stored npm_version '{value}'"]

    if not isinstance(npm_range, str) or not _satisfies_range(value, npm_range):
        errors.append(
            f"{label}: stored npm_version '{value}' does not satisfy engines.npm '{npm_range}'"
        )

    runtime_parsed = _parse_version(runtime_npm_version)
    if runtime_parsed is not None and parsed_value != runtime_parsed:
        errors.append(
            f"{label}: stored npm_version '{value}' does not match runtime {runtime_npm_version}"
        )
    return errors


def _extract_doc_version(text: str, patterns: list[str]) -> str | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).strip()
    return None


def _validate_doc_metadata(
    label: str,
    path: Path,
    nvmrc_major: str,
    node_range: str | None,
    npm_range: str | None,
    runtime_node_version: str,
    runtime_npm_version: str,
) -> list[str]:
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8", errors="ignore")
    node_value = _extract_doc_version(
        text,
        [
            r"-\s*node_version:\s*(v?\d+(?:\.\d+)*)",
            r"\*\*Node version\*\*:\s*(v?\d+(?:\.\d+)*)",
            r"Runtime baseline:.*?\bNode\s+(v?\d+(?:\.\d+)*)",
            r"\*\*Runtime baseline\*\*:\s*.*?\bNode\s+(v?\d+(?:\.\d+)*)",
        ],
    )
    npm_value = _extract_doc_version(
        text,
        [
            r"-\s*npm_version:\s*(v?\d+(?:\.\d+)*)",
            r"\*\*npm version\*\*:\s*(v?\d+(?:\.\d+)*)",
            r"Runtime baseline:.*?\bnpm\s+(v?\d+(?:\.\d+)*)",
            r"\*\*Runtime baseline\*\*:\s*.*?\bnpm\s+(v?\d+(?:\.\d+)*)",
        ],
    )

    errors = _validate_node_value(
        f"{label}:node_version",
        node_value,
        nvmrc_major,
        node_range,
        runtime_node_version,
    )
    errors.extend(
        _validate_npm_value(
            f"{label}:npm_version",
            npm_value,
            npm_range,
            runtime_npm_version,
        )
    )
    return errors


def _extract_log_value(text: str, prefix: str) -> str | None:
    match = re.search(rf"^{re.escape(prefix)}\s*(.+)$", text, flags=re.MULTILINE)
    if not match:
        return None
    return match.group(1).strip()


def _validate_log_metadata(
    label: str,
    path: Path,
    nvmrc_major: str,
    node_range: str | None,
    npm_range: str | None,
    runtime_node_version: str,
    runtime_npm_version: str,
) -> list[str]:
    if not path.exists():
        return []

    text = path.read_text(encoding="utf-8", errors="ignore")
    node_value = _extract_log_value(text, "NODE_VERSION:")
    npm_value = _extract_log_value(text, "NPM_VERSION:")

    errors = _validate_node_value(
        f"{label}:NODE_VERSION",
        node_value,
        nvmrc_major,
        node_range,
        runtime_node_version,
    )
    errors.extend(
        _validate_npm_value(
            f"{label}:NPM_VERSION",
            npm_value,
            npm_range,
            runtime_npm_version,
        )
    )
    return errors


def _validate_stored_metadata(
    repo_root: Path,
    nvmrc_major: str,
    node_range: str | None,
    npm_range: str | None,
    runtime_node_version: str,
    runtime_npm_version: str,
) -> list[str]:
    """Check that stored proof metadata node version agrees with .nvmrc policy.

    Reads ``release_gate.json`` and ``proof_manifest.json`` in
    ``artifacts/proof/current/`` for a ``node_version`` field, then compares
    the major version against the declared ``.nvmrc`` major.  Also checks
    ``CURRENT_PROOF.md`` for a ``node_version:`` line.

    Args:
        repo_root: Repository root directory.
        nvmrc_major: Major version string declared in ``.nvmrc`` (e.g. ``"20"``).

    Returns:
        List of error strings.  Empty means all stored metadata agrees.
    """
    errors: list[str] = []

    proof_json_files = {
        "release_gate.json": repo_root / "artifacts" / "proof" / "current" / "release_gate.json",
        "proof_manifest.json": repo_root / "artifacts" / "proof" / "current" / "proof_manifest.json",
    }
    for label, path in proof_json_files.items():
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{label}: failed to parse JSON: {exc}")
            continue
        stored_node = data.get("node_version") or data.get("gate_runner_node_version")
        stored_npm = data.get("npm_version")
        errors.extend(
            _validate_node_value(
                f"{label}:node_version",
                stored_node,
                nvmrc_major,
                node_range,
                runtime_node_version,
            )
        )
        errors.extend(
            _validate_npm_value(
                f"{label}:npm_version",
                stored_npm,
                npm_range,
                runtime_npm_version,
            )
        )

    doc_files = {
        "CURRENT_PROOF.md": repo_root / "CURRENT_PROOF.md",
        "PROOF_STATUS.md": repo_root / "PROOF_STATUS.md",
        "STATUS.md": repo_root / "STATUS.md",
    }
    for label, path in doc_files.items():
        errors.extend(
            _validate_doc_metadata(
                label,
                path,
                nvmrc_major,
                node_range,
                npm_range,
                runtime_node_version,
                runtime_npm_version,
            )
        )

    log_files = {
        "artifacts/proof/current/frontend_node_gate.log": repo_root / "artifacts" / "proof" / "current" / "frontend_node_gate.log",
    }
    for label, path in log_files.items():
        errors.extend(
            _validate_log_metadata(
                label,
                path,
                nvmrc_major,
                node_range,
                npm_range,
                runtime_node_version,
                runtime_npm_version,
            )
        )

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(REPO_ROOT), help="Repository root")
    args = parser.parse_args()

    repo_root = Path(args.root).resolve()
    root_nvmrc = repo_root / ".nvmrc"
    frontend_nvmrc = repo_root / "frontend" / ".nvmrc"
    package_json_path = repo_root / "frontend" / "package.json"

    root_major = _read_text(root_nvmrc) if root_nvmrc.exists() else None
    frontend_major = _read_text(frontend_nvmrc) if frontend_nvmrc.exists() else None
    package_json = json.loads(package_json_path.read_text(encoding="utf-8"))
    node_range = package_json.get("engines", {}).get("node")
    npm_range = package_json.get("engines", {}).get("npm")

    errors: list[str] = []
    if root_major is None and frontend_major is None:
        errors.append("missing .nvmrc policy files")
    elif root_major is not None and frontend_major is not None and root_major != frontend_major:
        errors.append(f".nvmrc mismatch: root={root_major} frontend={frontend_major}")

    declared_selector = root_major or frontend_major or ""
    declared_major = _major_from_policy(declared_selector)
    if declared_major is None:
        declared_selector = "0"
        declared_major = 0

    node_version, npm_version, runtime_source = _resolve_runtime_versions(
        declared_selector,
        declared_major,
        node_range,
    )

    parsed_node = _parse_version(node_version)
    if parsed_node is None:
        errors.append(f"Unable to parse node version: {node_version}")
    else:
        if parsed_node[0] != declared_major:
            errors.append(
                "Node major mismatch: "
                f"declared .nvmrc={declared_selector} but runtime is {node_version}"
            )
        if not isinstance(node_range, str) or not _satisfies_range(node_version, node_range):
            errors.append(
                f"Node runtime {node_version} does not satisfy frontend/package.json engines.node '{node_range}'"
            )

    if not isinstance(npm_range, str) or not _satisfies_range(npm_version, npm_range):
        errors.append(
            f"npm runtime {npm_version} does not satisfy frontend/package.json engines.npm '{npm_range}'"
        )

    # Validate stored proof metadata for node version drift
    metadata_errors = _validate_stored_metadata(
        repo_root,
        declared_selector,
        node_range,
        npm_range,
        node_version,
        npm_version,
    )
    errors.extend(metadata_errors)

    print(f"NODE_VERSION: {node_version}")
    print(f"NPM_VERSION: {npm_version}")
    print(f"RUNTIME_SOURCE: {runtime_source}")
    print(f"ROOT_NVMRC: {root_major if root_major is not None else '<missing>'}")
    print(f"FRONTEND_NVMRC: {frontend_major if frontend_major is not None else '<missing>'}")
    print(f"NODE_RANGE: {node_range}")
    print(f"NPM_RANGE: {npm_range}")
    print(f"DECLARED_NODE_MAJOR: {declared_major}")
    print(f"DECLARED_NODE_SELECTOR: {declared_selector}")

    if errors:
        print("NODE_POLICY: FAIL")
        for error in errors:
            print(f"ERROR: {error}")
        return 1

    print("NODE_POLICY: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())