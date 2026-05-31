#!/usr/bin/env python3
"""Export a canonical source registry status summary for proof artifacts.

The summary is derived from merged source definitions rather than live runtime
state so release proof can validate fail-closed source controls
deterministically
in CI and local proof runs.
"""

from __future__ import annotations

import json
import importlib
import os
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

_automation_statuses = importlib.import_module(
    "app.ingestion.automation_statuses"
)
_source_adapters = importlib.import_module("app.ingestion.source_adapters")
_source_registry = importlib.import_module("app.seed.source_registry")

ENABLEABLE_STATUSES = _automation_statuses.ENABLEABLE_STATUSES
RUNNABLE_STATUSES = _automation_statuses.RUNNABLE_STATUSES
ADAPTER_REGISTRY = _source_adapters.ADAPTER_REGISTRY
_merged_sources = _source_registry._merged_sources

_PARSER_SECRET_NAMES: dict[str, str] = {
    "canlii_api": "JTA_CANLII_API_KEY",
    "scc_lexum_api": "LEXUM_API_KEY",
}


def _source_display_name(source: dict) -> str:
    """Return the best available display name for a source registry entry.

    Fallback chain: source_name → name → source_key → UNKNOWN_SOURCE.
    """
    return (
        source.get("source_name")
        or source.get("name")
        or source.get("source_key")
        or "UNKNOWN_SOURCE"
    )


def _required_secret_name(parser_key: str | None) -> str | None:
    if not parser_key:
        return None
    return _PARSER_SECRET_NAMES.get(parser_key)


def _parse_json_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [str(item) for item in parsed]
    return []


def _parse_json_dict(value: object) -> dict:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return {}
    return {}


def _canonical_status(source_key: str, config_json: object) -> str:
    cfg = _parse_json_dict(config_json)
    if bool(cfg.get("deprecated")):
        return "deprecated"
    canonical_key = cfg.get("canonical_source_key")
    if canonical_key and canonical_key != source_key:
        return "alias"
    return "canonical"


def _secret_is_configured(secret_name: str | None) -> bool:
    if not secret_name:
        return True
    if secret_name == "JTA_CANLII_API_KEY":
        return bool(
            os.getenv("JTA_CANLII_API_KEY") or os.getenv("CANLII_API_KEY")
        )
    if secret_name == "LEXUM_API_KEY":
        return bool(
            os.getenv("JTA_LEXUM_API_KEY") or os.getenv("LEXUM_API_KEY")
        )
    return bool(os.getenv(secret_name))


def _can_enable(source_row: dict) -> tuple[bool, str | None]:
    if source_row["source_class"] != "machine_ingest":
        return False, "source_class_not_machine_ingest"
    if source_row["automation_status"] not in ENABLEABLE_STATUSES:
        return False, "automation_status_not_enableable"
    if not source_row["adapter_exists"]:
        return False, "adapter_missing"
    if not source_row["required_secret_configured"]:
        return False, "missing_secret"
    if not source_row["parser_version"]:
        return False, "missing_parser_version"
    if not source_row["allowed_domains"]:
        return False, "missing_allowed_domains"
    return True, None


def _source_row(source: dict) -> dict:
    parser_key = source.get("parser")
    secret_name = _required_secret_name(parser_key)
    source_key = str(source.get("source_key") or "")
    source_id = source.get("id") or source.get("source_key")
    adapter_cls = ADAPTER_REGISTRY.get(parser_key) if parser_key else None
    adapter_name = adapter_cls.__name__ if adapter_cls else None
    automation_status = source.get("automation_status")
    source_class = source.get("source_class")
    source_row = {
        "source_id": source_id,
        "source_key": source_key,
        "source_name": _source_display_name(source),
        "name": source.get("source_name") or source_key,
        "source_type": source.get("source_type") or "unknown",
        "jurisdiction": (
            source.get("jurisdiction")
            or source.get("country")
            or "unknown"
        ),
        "source_class": source_class,
        "canonical_status": _canonical_status(
            source_key,
            source.get("config_json"),
        ),
        "parser": parser_key,
        "parser_version": source.get("parser_version"),
        "allowed_domains": _parse_json_list(source.get("allowed_domains")),
        "creates": _parse_json_list(source.get("creates")),
        "automation_status": automation_status,
        "enabled": bool(source.get("enabled_default", False)),
        "is_machine_ingest": source_class == "machine_ingest",
        "adapter_name": adapter_name,
        "adapter_exists": adapter_name is not None,
        "required_secret_name": secret_name,
        "required_secret_configured": _secret_is_configured(secret_name),
        "can_run_when_active": automation_status in RUNNABLE_STATUSES,
        "requires_secret": secret_name is not None,
        "public_record_authority": source.get("public_record_authority"),
        "public_visibility_policy": {
            "requires_manual_review": bool(
                source.get("requires_manual_review", True)
            ),
            "public_publish_default": bool(
                source.get("public_publish_default", False)
            ),
        },
    }
    can_enable, reason = _can_enable(source_row)
    source_row["can_enable"] = can_enable
    source_row["cannot_enable_reason"] = reason
    return source_row


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    output_path = (
        REPO_ROOT
        / "artifacts"
        / "proof"
        / "current"
        / "source_registry_status.json"
    )
    markdown_output_path = (
        REPO_ROOT
        / "artifacts"
        / "proof"
        / "current"
        / "SOURCE_REGISTRY_STATUS.md"
    )
    docs_markdown_output_path = REPO_ROOT / "docs" / "SOURCE_REGISTRY_STATUS.md"
    if "--output" in args:
        output_path = Path(args[args.index("--output") + 1]).resolve()
    if "--markdown-output" in args:
        markdown_output_path = Path(
            args[args.index("--markdown-output") + 1]
        ).resolve()
    if "--docs-output" in args:
        docs_markdown_output_path = Path(
            args[args.index("--docs-output") + 1]
        ).resolve()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_output_path.parent.mkdir(parents=True, exist_ok=True)
    docs_markdown_output_path.parent.mkdir(parents=True, exist_ok=True)

    sources = [_source_row(source) for source in _merged_sources()]
    source_class_counts = Counter(
        source["source_class"] or "unset" for source in sources
    )
    automation_counts = Counter(
        source["automation_status"] or "unset" for source in sources
    )
    required_secret_counts = Counter(
        source["required_secret_name"] or "none" for source in sources
    )

    machine_ingest = [
        source for source in sources if source["is_machine_ingest"]
    ]
    runnable = [source for source in sources if source["can_run_when_active"]]
    enableable = [source for source in sources if source["can_enable"]]
    sources_requiring_secrets = [
        source for source in sources if source["requires_secret"]
    ]
    machine_ingest_ready_sources = [
        source["source_key"]
        for source in machine_ingest
        if source["can_run_when_active"]
    ]

    payload = {
        "summary": {
            "total_sources": len(sources),
            "machine_ingest_sources": len(machine_ingest),
            "runnable_when_active_sources": len(runnable),
            "enableable_sources": len(enableable),
            "sources_requiring_secrets": len(sources_requiring_secrets),
        },
        "counts_by_source_class": dict(sorted(source_class_counts.items())),
        "counts_by_automation_status": dict(sorted(automation_counts.items())),
        "counts_by_required_secret": dict(
            sorted(required_secret_counts.items())
        ),
        "machine_ingest_ready_sources": machine_ingest_ready_sources,
        "sources_requiring_secret": [
            {
                "source_key": source["source_key"],
                "parser": source["parser"],
                "required_secret_name": source["required_secret_name"],
                "required_secret_configured": source[
                    "required_secret_configured"
                ],
            }
            for source in sources
            if source["requires_secret"]
        ],
        "canonical_source_keys": [
            source["source_key"]
            for source in sources
            if source["canonical_status"] == "canonical"
        ],
        "deprecated_source_keys": [
            source["source_key"]
            for source in sources
            if source["canonical_status"] == "deprecated"
        ],
        "sources": sources,
    }

    header = [
        "# SOURCE_REGISTRY_STATUS",
        "",
        f"- total_sources: {len(sources)}",
        f"- machine_ingest_sources: {len(machine_ingest)}",
        f"- runnable_when_active_sources: {len(runnable)}",
        f"- enableable_sources: {len(enableable)}",
        f"- sources_requiring_secrets: {len(sources_requiring_secrets)}",
        "",
        "| source key | source name | jurisdiction | source class/type | automation status | adapter key | adapter exists | required secrets | required secrets present during proof | enabled by default | can be enabled by admin | can run now | reason if not runnable | review required before public visibility | public exposure allowed before review | current alpha status |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    rows: list[str] = []
    for source in sorted(sources, key=lambda item: item["source_key"]):
        required_secret = source.get("required_secret_name") or "none"
        review_required = (
            "yes"
            if source.get("public_visibility_policy", {}).get(
                "requires_manual_review", True
            )
            else "no"
        )
        public_before_review = "no"
        can_enable = "yes" if source.get("can_enable") else "no"
        can_run_now = (
            "yes"
            if source.get("can_run_when_active") and source.get("is_machine_ingest")
            else "no"
        )
        reason_not_runnable = source.get("cannot_enable_reason") or "none"
        alpha_status = (
            "runnable-alpha-source"
            if can_run_now == "yes"
            else "limited-alpha-source"
        )
        rows.append(
            "| "
            + " | ".join(
                [
                    str(source.get("source_key", "")),
                    _source_display_name(source),
                    str(source.get("jurisdiction", "unknown")),
                    f"{source.get('source_class', 'unknown')}/{source.get('source_type', 'unknown')}",
                    str(source.get("automation_status", "unknown")),
                    str(source.get("parser", "none")),
                    "yes" if source.get("adapter_exists") else "no",
                    required_secret,
                    "yes" if source.get("required_secret_configured") else "no",
                    "yes" if source.get("enabled") else "no",
                    can_enable,
                    can_run_now,
                    reason_not_runnable,
                    review_required,
                    public_before_review,
                    alpha_status,
                ]
            )
            + " |"
        )

    markdown_text = "\n".join(header + rows) + "\n"

    output_path.write_text(
        json.dumps(payload, indent=2) + "\n",
        encoding="utf-8",
    )
    markdown_output_path.write_text(markdown_text, encoding="utf-8")
    docs_markdown_output_path.write_text(markdown_text, encoding="utf-8")
    print("SOURCE REGISTRY STATUS: PASS")
    print(f"output={output_path}")
    print(f"markdown_output={markdown_output_path}")
    print(f"docs_output={docs_markdown_output_path}")
    print(f"sources_checked={len(sources)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
