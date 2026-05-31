#!/usr/bin/env python3
"""Run npm audit and fail unless EVERY vulnerable package is covered in the triage doc.

Per-package triage matching: each package name reported by `npm audit` must
appear literally in FRONTEND_SECURITY_TRIAGE.md. A triage document that merely
exists is not sufficient — coverage must be explicit.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
import re
from datetime import date

REPO_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = REPO_ROOT / "frontend"
TRIAGE_DOC = REPO_ROOT / "docs" / "security" / "FRONTEND_SECURITY_TRIAGE.md"
EXCEPTIONS_DOC = (
    REPO_ROOT / "docs" / "security" / "frontend_dependency_exceptions.md"
)


def _triaged_packages(triage_text: str) -> set[str]:
    """Return the set of package names mentioned in the triage document.

    Looks for backtick-quoted package names, e.g. `glob` or `@next/eslint-plugin-next`.
    """
    import re
    return set(re.findall(r"`([^`]+)`", triage_text))


def _vulnerability_by_package(payload: dict) -> dict[str, dict]:
    vulnerabilities = payload.get("vulnerabilities")
    if not isinstance(vulnerabilities, dict):
        return {}
    return {
        pkg: data
        for pkg, data in vulnerabilities.items()
        if isinstance(pkg, str) and isinstance(data, dict)
    }


def _severity_for_package(vuln: dict) -> str:
    severity = vuln.get("severity")
    if isinstance(severity, str):
        return severity.strip().lower()
    return "unknown"


def _advisory_ids_for_package(vuln: dict) -> set[str]:
    advisory_ids: set[str] = set()
    via = vuln.get("via")
    if not isinstance(via, list):
        return advisory_ids
    for item in via:
        if isinstance(item, str):
            advisory_ids.add(item)
            continue
        if not isinstance(item, dict):
            continue
        source = item.get("source")
        if isinstance(source, int):
            advisory_ids.add(str(source))
        elif isinstance(source, str) and source:
            advisory_ids.add(source)
        for key in ("url", "name", "title"):
            value = item.get(key)
            if isinstance(value, str) and value:
                advisory_ids.add(value)
    return advisory_ids


def _section_for_package(triage_text: str, package_name: str) -> str:
    pattern = re.compile(
        r"(^###\s+.*?`" + re.escape(package_name) + r"`.*?$)(.*?)(?=^###\s+|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(triage_text)
    if not m:
        return ""
    return (m.group(1) + "\n" + m.group(2)).strip()


def _missing_exception_fields(section_text: str) -> list[str]:
    required = {
        "package": ["**package**", "package:"],
        "version": ["**version**", "version:"],
        "vulnerability_id": [
            "**vulnerability id**",
            "ghsa-",
            "cve-",
            "advisory",
        ],
        "reason_not_exploitable": [
            "**reason it is not exploitable**",
            "not exploitable",
        ],
        "mitigation": ["**mitigation**", "mitigation:"],
        "expiry_date": ["**expiry date**", "expiry"],
        "owner": ["**owner**", "owner:"],
    }
    text = section_text.lower()
    missing: list[str] = []
    for key, tokens in required.items():
        if not any(token in text for token in tokens):
            missing.append(key)
    return missing


def _extract_expiry_date(section_text: str) -> date | None:
    match = re.search(r"(\d{4}-\d{2}-\d{2})", section_text)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(1))
    except ValueError:
        return None


def _missing_required_fields(section_text: str) -> list[str]:
    required = {
        "severity": ["**Severity**", "severity"],
        "via_chain": ["via", "dependency chain", "transitive via"],
        "fix_availability": ["fix", "patch", "availability"],
        "dependency_scope": ["direct", "transitive"],
        "runtime_scope": ["runtime", "dev-only", "build-time", "production"],
        "owner": ["**Owner**", "owner"],
        "rationale": ["rationale", "decision", "accepted"],
        "target_fix": ["target", "date", "condition", "upstream"],
    }
    text = section_text.lower()
    missing: list[str] = []
    for key, tokens in required.items():
        if not any(token.lower() in text for token in tokens):
            missing.append(key)
    return missing


def main() -> int:
    print("NPM AUDIT TRIAGE")

    proc = subprocess.run(
        ["npm", "audit", "--json", "--prefix", str(FRONTEND_DIR)],
        capture_output=True,
        text=True,
        check=False,
    )

    total = 0
    vulnerable_packages: list[str] = []
    vulnerability_by_package: dict[str, dict] = {}
    try:
        payload = json.loads(proc.stdout or "{}")
        meta = payload.get("metadata", {}).get("vulnerabilities", {})
        total = int(meta.get("total", 0))
        vulnerability_by_package = _vulnerability_by_package(payload)
        vulnerable_packages = list(vulnerability_by_package.keys())
    except Exception:
        payload = {}

    print(f"vulnerabilities={total}")

    if total == 0:
        print("RESULT: PASS no_vulnerabilities")
        return 0

    # Vulnerabilities found — verify every package is in the triage doc
    if not TRIAGE_DOC.exists():
        print(f"RESULT: FAIL missing_triage_doc={TRIAGE_DOC.relative_to(REPO_ROOT)}")
        return 1

    triage_text = TRIAGE_DOC.read_text(encoding="utf-8")
    triaged = _triaged_packages(triage_text)
    print(f"triage_doc={TRIAGE_DOC.relative_to(REPO_ROOT)}")
    print(f"triaged_packages_in_doc={len(triaged)}")
    print(f"vulnerable_packages={len(vulnerable_packages)}")

    untriaged = [pkg for pkg in vulnerable_packages if pkg not in triaged]
    if untriaged:
        print("RESULT: FAIL untriaged_packages")
        for pkg in untriaged:
            print(f"  - untriaged: {pkg}")
        return 1

    incomplete_sections: list[str] = []
    for pkg in vulnerable_packages:
        section = _section_for_package(triage_text, pkg)
        if not section:
            incomplete_sections.append(f"{pkg}:missing_section")
            continue
        missing = _missing_required_fields(section)
        if missing:
            incomplete_sections.append(f"{pkg}:missing_fields={','.join(missing)}")

    if incomplete_sections:
        print("RESULT: FAIL incomplete_triage_metadata")
        for item in incomplete_sections:
            print(f"  - {item}")
        return 1

    high_or_critical = [
        pkg
        for pkg, vuln in vulnerability_by_package.items()
        if _severity_for_package(vuln) in {"high", "critical"}
    ]
    if high_or_critical:
        if not EXCEPTIONS_DOC.exists():
            print(
                "RESULT: FAIL missing_frontend_dependency_exceptions="
                f"{EXCEPTIONS_DOC.relative_to(REPO_ROOT)}"
            )
            return 1

        exceptions_text = EXCEPTIONS_DOC.read_text(encoding="utf-8")
        exception_failures: list[str] = []
        today = date.today()
        for pkg in high_or_critical:
            section = _section_for_package(exceptions_text, pkg)
            if not section:
                exception_failures.append(f"{pkg}:missing_exception_section")
                continue

            missing_fields = _missing_exception_fields(section)
            if missing_fields:
                exception_failures.append(
                    f"{pkg}:missing_exception_fields={','.join(missing_fields)}"
                )

            expiry = _extract_expiry_date(section)
            if expiry is None:
                exception_failures.append(f"{pkg}:invalid_or_missing_expiry_date")
            elif expiry < today:
                exception_failures.append(
                    f"{pkg}:expired_exception={expiry.isoformat()}"
                )

            advisory_ids = _advisory_ids_for_package(vulnerability_by_package[pkg])
            section_lower = section.lower()
            if advisory_ids and not any(token.lower() in section_lower for token in advisory_ids):
                exception_failures.append(
                    f"{pkg}:missing_vulnerability_id_reference"
                )

        if exception_failures:
            print("RESULT: FAIL invalid_frontend_dependency_exceptions")
            for item in exception_failures:
                print(f"  - {item}")
            return 1

    print("RESULT: PASS all_packages_triaged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
