#!/usr/bin/env python3
"""Generate source coverage matrix markdown from source_registry_status.json."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_REGISTRY = Path("artifacts/proof/current/source_registry_status.json")
DEFAULT_OUTPUT = Path("docs/source-governance/COVERAGE_MATRIX.md")


def _normalize(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _escape_cell(value: object) -> str:
    return _normalize(value).replace("|", "\\|")


def _load_registry(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Registry payload must be a JSON object")
    return payload


def _render_summary(summary: dict) -> list[str]:
    keys = (
        "total_sources",
        "machine_ingest_sources",
        "runnable_now",
        "enable_ready",
        "deprecated",
    )
    lines = ["## Summary", ""]
    for key in keys:
        if key in summary:
            lines.append(f"- {key}: {_normalize(summary[key])}")
    lines.append("")
    return lines


def _render_table(sources: list[dict]) -> list[str]:
    lines = [
        "## Sources",
        "",
        "| source key | jurisdiction | class | lifecycle | automation | runnable | enable ready | parser | adapter status | next action |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for source in sorted(
        sources,
        key=lambda item: (_normalize(item.get("source_key"))).lower(),
    ):
        lines.append(
            "| "
            + " | ".join(
                [
                    _escape_cell(source.get("source_key")),
                    _escape_cell(source.get("jurisdiction")),
                    _escape_cell(source.get("source_class")),
                    _escape_cell(source.get("lifecycle_state")),
                    _escape_cell(source.get("automation_status")),
                    _escape_cell(source.get("runnable_now")),
                    _escape_cell(source.get("enable_ready")),
                    _escape_cell(source.get("parser")),
                    _escape_cell(source.get("adapter_state")),
                    _escape_cell(source.get("operator_next_step")),
                ]
            )
            + " |"
        )
    lines.append("")
    return lines


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", default=str(DEFAULT_REGISTRY))
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()

    registry_path = Path(args.registry).resolve()
    output_path = Path(args.output).resolve()

    if not registry_path.is_file():
        raise SystemExit(f"registry_not_found:{registry_path}")

    payload = _load_registry(registry_path)
    summary = payload.get("summary")
    sources = payload.get("sources")

    if not isinstance(summary, dict):
        raise SystemExit("registry_missing_summary")
    if not isinstance(sources, list):
        raise SystemExit("registry_missing_sources")

    generated_at = datetime.now(timezone.utc).isoformat()

    lines: list[str] = [
        "# Source Coverage Matrix",
        "",
        "Generated from artifacts/proof/current/source_registry_status.json.",
        f"Generated at: {generated_at}",
        "",
    ]
    lines.extend(_render_summary(summary))
    lines.extend(_render_table([item for item in sources if isinstance(item, dict)]))
    lines.extend(
        [
            "## Notes",
            "",
            "- source_registry_status.json is authoritative.",
            "- Evidence snapshots are authoritative; AI and memory outputs are derivative.",
            "- Public data remains review-gated in alpha.",
            "",
        ]
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote coverage matrix: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
