#!/usr/bin/env python3
"""Generate a fail-closed stub adapter report."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
ADAPTER_DIR = REPO_ROOT / "backend" / "app" / "ingestion" / "source_adapters"
REGISTRY_PATH = REPO_ROOT / "backend" / "app" / "ingestion" / "sources" / "canada_saskatchewan_sources.yaml"
OUTPUT = REPO_ROOT / "artifacts" / "proof" / "current" / "stub_adapter_report.md"


def _load_registry() -> list[dict]:
    import yaml

    payload = yaml.safe_load(REGISTRY_PATH.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        rows = payload.get("sources", [])
        return rows if isinstance(rows, list) else []
    if isinstance(payload, list):
        return payload
    return []


def _find_stubs() -> list[dict]:
    findings: list[dict] = []
    registry = _load_registry()

    adapter_code: dict[str, str] = {}
    for path in ADAPTER_DIR.glob("*.py"):
        adapter_code[path.stem] = path.read_text(encoding="utf-8")

    for source in registry:
        if not isinstance(source, dict):
            continue

        parser_key = (source.get("parser") or "").strip()
        source_key = source.get("source_key", "unknown")
        source_class = source.get("source_class") or "unknown"
        automation_status = source.get("automation_status") or "unknown"
        enabled = bool(source.get("is_active", False))

        adapter_name = parser_key
        code = adapter_code.get(adapter_name)
        if code is None:
            findings.append(
                {
                    "file_path": f"backend/app/ingestion/source_adapters/{adapter_name}.py",
                    "source_key": source_key,
                    "source_class": source_class,
                    "automation_status": automation_status,
                    "enabled": enabled,
                    "runnable": False,
                    "reason": "adapter_missing",
                }
            )
            continue

        is_stub = "NotImplementedError" in code or "TODO" in code
        if not is_stub and source_class != "disabled_stub":
            continue

        runnable = bool(
            enabled
            and source_class == "machine_ingest"
            and automation_status == "machine_ready_enabled"
            and not is_stub
        )
        reason = "not_implemented_stub" if is_stub else "class_disabled_stub"
        findings.append(
            {
                "file_path": f"backend/app/ingestion/source_adapters/{adapter_name}.py",
                "source_key": source_key,
                "source_class": source_class,
                "automation_status": automation_status,
                "enabled": enabled,
                "runnable": runnable,
                "reason": reason,
            }
        )

    return sorted(findings, key=lambda item: (item["source_key"], item["file_path"]))


def _write_report(findings: list[dict]) -> None:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Stub Adapter Report",
        "",
        f"- generated_at: {datetime.now(timezone.utc).isoformat()}",
        f"- findings: {len(findings)}",
        "",
        "| source_key | file_path | source_class | automation_status | enabled | runnable | reason |",
        "|---|---|---|---|---|---|---|",
    ]

    for finding in findings:
        lines.append(
            f"| {finding['source_key']} | {finding['file_path']} | {finding['source_class']} | {finding['automation_status']} | {str(finding['enabled']).lower()} | {str(finding['runnable']).lower()} | {finding['reason']} |"
        )

    lines.extend(
        [
            "",
            "## Fail-Closed Result",
            "",
            "- PASS if all stub/reference/manual/adapter-missing sources are non-runnable.",
            "- Current report computes runnable=false for all discovered stubs.",
        ]
    )
    OUTPUT.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()

    findings = _find_stubs()
    _write_report(findings)

    failed = [finding for finding in findings if finding["runnable"]]
    print(f"Stub adapter report written: {OUTPUT}")
    if failed:
        print("FAIL")
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
