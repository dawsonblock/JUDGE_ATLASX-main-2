#!/usr/bin/env python3
"""Validate source-registry documentation claims against YAML + adapter registry."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    from app.ingestion.source_adapters import ADAPTER_REGISTRY  # noqa: E402
except Exception:  # pragma: no cover - gate runner compatibility fallback
    ADAPTER_REGISTRY = {}

ROOT_MD_EXCLUDE = {
    "REPAIR_REPORT.md",
    "CURRENT_ALPHA_STATUS.md",
    "SOURCE_REGISTRY_STATUS.md",
    "PROOF_POLICY.md",
}

REQUIRED_SUMMARY_METRICS = (
    "total_sources",
    "machine_ingest_sources",
    "runnable_now",
    "enable_ready",
    "deprecated",
)

REQUIRED_DERIVED_METRICS = (
    "machine_ready_disabled",
    "adapter_missing",
)

REQUIRED_DOC_METRICS = REQUIRED_SUMMARY_METRICS + REQUIRED_DERIVED_METRICS

SOURCE_REGISTRY_HEADER_ALIASES: dict[str, tuple[str, ...]] = {
    "source key": ("source key", "source_key"),
    "lifecycle state": ("lifecycle state", "lifecycle"),
    "automation status": ("automation status", "automation"),
    "adapter state": ("adapter state",),
    "adapter exists": ("adapter exists",),
    "runnable now": ("runnable now",),
    "enable ready": ("enable ready",),
    "review required": ("review required",),
}

REQUIRED_SOURCE_REGISTRY_HEADERS = (
    "source key",
    "lifecycle state",
    "automation status",
    "adapter state",
    "runnable now",
    "enable ready",
    "review required",
)


def _load_yaml_sources() -> list[dict]:
    yaml_path = (
        REPO_ROOT
        / "backend"
        / "app"
        / "ingestion"
        / "sources"
        / "canada_saskatchewan_sources.yaml"
    )
    data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    return list(data.get("sources", []))


def _load_source_truth() -> tuple[dict[str, int], set[str], set[str], dict[str, dict]]:
    truth_path = REPO_ROOT / "artifacts" / "proof" / "current" / "source_registry_status.json"
    payload = json.loads(truth_path.read_text(encoding="utf-8"))
    summary = payload.get("summary") or {}

    summary_counts: dict[str, int] = {}
    for metric in REQUIRED_SUMMARY_METRICS:
        value = summary.get(metric)
        if isinstance(value, int):
            summary_counts[metric] = value

    sources = payload.get("sources") or []
    source_truth_by_key = {
        str(source.get("source_key")): source
        for source in sources
        if source.get("source_key")
    }

    derived_counts = {
        "machine_ready_disabled": sum(
            1 for source in sources if source.get("automation_status") == "machine_ready_disabled"
        ),
        "adapter_missing": sum(
            1 for source in sources if source.get("automation_status") == "adapter_missing"
        ),
    }
    summary_counts.update(derived_counts)

    enable_ready_ids = {
        str(source.get("source_key"))
        for source in sources
        if source.get("enable_ready") is True and source.get("source_key")
    }
    runnable_ids = {
        str(source.get("source_key"))
        for source in sources
        if source.get("runnable_now") is True and source.get("source_key")
    }

    return summary_counts, enable_ready_ids, runnable_ids, source_truth_by_key


def _collect_doc_texts() -> list[tuple[Path, str]]:
    paths = [REPO_ROOT / "README.md"]
    for path in REPO_ROOT.glob("*.md"):
        if path.name in ROOT_MD_EXCLUDE:
            continue
        paths.append(path)
    paths.extend((REPO_ROOT / "docs").glob("**/*.md"))
    out: list[tuple[Path, str]] = []
    for path in paths:
        if path.exists():
            out.append((path, path.read_text(encoding="utf-8", errors="ignore")))
    return out


def _extract_metric_value(text: str, metric: str) -> int | None:
    patterns = (
        rf"-\s*`?{re.escape(metric)}`?\s*:\s*(\d+)",
        rf"\|\s*`?{re.escape(metric)}`?\s*\|\s*(\d+)\s*\|",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1))
    return None


def _extract_h2_section(text: str, heading: str) -> str:
    lines = text.splitlines()
    start_index: int | None = None
    for idx, line in enumerate(lines):
        if line.strip() == f"## {heading}":
            start_index = idx + 1
            break
    if start_index is None:
        return ""

    end_index = len(lines)
    for idx in range(start_index, len(lines)):
        if lines[idx].startswith("## "):
            end_index = idx
            break

    return "\n".join(lines[start_index:end_index])


def _extract_table_source_keys(section_text: str) -> set[str]:
    keys: set[str] = set()
    for line in section_text.splitlines():
        match = re.match(r"^\|\s*`([^`]+)`\s*\|", line.strip())
        if match:
            key = match.group(1).strip()
            if key:
                keys.add(key)
    return keys


def _extract_checklist_source_keys(text: str) -> set[str]:
    return {
        match.group(1).strip()
        for match in re.finditer(r"^###\s+`([^`]+)`\s*$", text, re.MULTILINE)
        if match.group(1).strip()
    }


def _parse_bool_cell(value: str) -> bool | None:
    cell = value.strip().strip("`").lower()
    if "✓" in cell or cell in {"true", "yes", "y", "1"}:
        return True
    if "✗" in cell or cell in {"false", "no", "n", "0"}:
        return False
    return None


def _normalize_header(value: str) -> str:
    return " ".join(value.strip().strip("`").lower().split())


def _extract_source_registry_header_map(text: str) -> dict[str, int]:
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        normalized = [_normalize_header(cell) for cell in cells]
        if "source key" not in normalized:
            continue
        return {header: idx for idx, header in enumerate(normalized) if header}
    return {}


def _resolve_source_registry_headers(header_map: dict[str, int]) -> dict[str, int]:
    resolved: dict[str, int] = {}
    for canonical, aliases in SOURCE_REGISTRY_HEADER_ALIASES.items():
        for alias in aliases:
            if alias in header_map:
                resolved[canonical] = header_map[alias]
                break
        if canonical in resolved:
            continue
        if canonical == "review required":
            for header, idx in header_map.items():
                if header.startswith("review required"):
                    resolved[canonical] = idx
                    break
    return resolved


def _validate_doc_metrics(doc_path: Path, summary_counts: dict[str, int]) -> list[str]:
    errors: list[str] = []
    if not doc_path.exists():
        return [f"{doc_path.relative_to(REPO_ROOT)}:missing"]

    text = doc_path.read_text(encoding="utf-8", errors="ignore")
    rel = doc_path.relative_to(REPO_ROOT)
    for metric in REQUIRED_DOC_METRICS:
        expected = summary_counts.get(metric)
        if expected is None:
            errors.append(
                "artifacts/proof/current/source_registry_status.json"
                f":missing_summary_metric:{metric}"
            )
            continue
        observed = _extract_metric_value(text, metric)
        if observed is None:
            errors.append(f"{rel}:metric_missing:{metric}")
        elif observed != expected:
            errors.append(f"{rel}:metric_mismatch:{metric}:{observed}!={expected}")
    return errors


def _check_id_set_diff(
    rel: Path,
    field: str,
    expected_ids: set[str],
    documented_ids: set[str],
) -> list[str]:
    errors: list[str] = []
    missing_ids = sorted(expected_ids - documented_ids)
    extra_ids = sorted(documented_ids - expected_ids)
    if missing_ids:
        errors.append(f"{rel}:{field}_missing:{','.join(missing_ids)}")
    if extra_ids:
        errors.append(f"{rel}:{field}_extra:{','.join(extra_ids)}")
    return errors


def _validate_governance_docs(
    summary_counts: dict[str, int],
    enable_ready_ids: set[str],
    runnable_ids: set[str],
) -> list[str]:
    errors: list[str] = []

    real_doc = REPO_ROOT / "docs" / "source-governance" / "REAL_AUTOMATION_STATUS.md"
    checklist_doc = REPO_ROOT / "docs" / "source-governance" / "SOURCE_ENABLEMENT_CHECKLIST.md"

    for doc_path in (real_doc, checklist_doc):
        errors.extend(_validate_doc_metrics(doc_path, summary_counts))

    if real_doc.exists():
        text = real_doc.read_text(encoding="utf-8", errors="ignore")
        rel = real_doc.relative_to(REPO_ROOT)

        enabled_section = _extract_h2_section(text, "Enabled Source (Production)")
        ready_disabled_section = _extract_h2_section(text, "Ready But Disabled (Alpha Scope)")

        documented_runnable = _extract_table_source_keys(enabled_section)
        documented_enable_ready = _extract_table_source_keys(ready_disabled_section)

        errors.extend(
            _check_id_set_diff(
                rel=rel,
                field="runnable_now_ids",
                expected_ids=runnable_ids,
                documented_ids=documented_runnable,
            )
        )
        errors.extend(
            _check_id_set_diff(
                rel=rel,
                field="enable_ready_ids",
                expected_ids=enable_ready_ids,
                documented_ids=documented_enable_ready,
            )
        )

    if checklist_doc.exists():
        text = checklist_doc.read_text(encoding="utf-8", errors="ignore")
        rel = checklist_doc.relative_to(REPO_ROOT)
        checklist_ids = _extract_checklist_source_keys(text)
        errors.extend(
            _check_id_set_diff(
                rel=rel,
                field="enable_ready_ids",
                expected_ids=enable_ready_ids,
                documented_ids=checklist_ids,
            )
        )

    return errors


def _validate_source_registry_row(
    source_key: str,
    cells: list[str],
    truth: dict,
    resolved_header_map: dict[str, int],
) -> list[str]:
    errors: list[str] = []
    required_headers = ("lifecycle state", "automation status", "runnable now", "enable ready")
    max_required_index = max(resolved_header_map[header] for header in required_headers)
    if len(cells) <= max_required_index:
        return [f"docs/SOURCE_REGISTRY_STATUS.md:row_malformed:{source_key}"]

    lifecycle_doc = cells[resolved_header_map["lifecycle state"]].strip("`").strip()
    automation_doc = cells[resolved_header_map["automation status"]].strip("`").strip()
    runnable_doc = _parse_bool_cell(cells[resolved_header_map["runnable now"]])
    enable_ready_doc = _parse_bool_cell(cells[resolved_header_map["enable ready"]])

    lifecycle_truth = str(truth.get("lifecycle_state") or "")
    automation_truth = str(truth.get("automation_status") or "")
    runnable_truth = bool(truth.get("runnable_now"))
    enable_ready_truth = bool(truth.get("enable_ready"))

    if lifecycle_doc != lifecycle_truth:
        errors.append(
            "docs/SOURCE_REGISTRY_STATUS.md:lifecycle_mismatch:"
            f"{source_key}:{lifecycle_doc}!={lifecycle_truth}"
        )
    if automation_doc != automation_truth:
        errors.append(
            "docs/SOURCE_REGISTRY_STATUS.md:automation_mismatch:"
            f"{source_key}:{automation_doc}!={automation_truth}"
        )
    if runnable_doc is None:
        errors.append(
            "docs/SOURCE_REGISTRY_STATUS.md:runnable_cell_unparseable:"
            f"{source_key}"
        )
    elif runnable_doc != runnable_truth:
        errors.append(
            "docs/SOURCE_REGISTRY_STATUS.md:runnable_mismatch:"
            f"{source_key}:{int(runnable_doc)}!={int(runnable_truth)}"
        )
    if enable_ready_doc is None:
        errors.append(
            "docs/SOURCE_REGISTRY_STATUS.md:enable_ready_cell_unparseable:"
            f"{source_key}"
        )
    elif enable_ready_doc != enable_ready_truth:
        errors.append(
            "docs/SOURCE_REGISTRY_STATUS.md:enable_ready_mismatch:"
            f"{source_key}:{int(enable_ready_doc)}!={int(enable_ready_truth)}"
        )

    return errors


def _parse_source_registry_rows(text: str) -> tuple[set[str], dict[str, list[str]]]:
    row_keys: set[str] = set()
    row_cells_by_key: dict[str, list[str]] = {}
    skip_keys = {"source key", "source_key", "---"}

    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if not cells:
            continue
        first = cells[0].strip("`").strip()
        first_lower = first.lower()
        if first_lower in skip_keys or first.startswith(":") or first in {"↳", "->"}:
            continue
        if first:
            row_keys.add(first)
            row_cells_by_key[first] = cells

    return row_keys, row_cells_by_key


def _validate_source_registry_headers(resolved_header_map: dict[str, int]) -> list[str]:
    missing = [header for header in REQUIRED_SOURCE_REGISTRY_HEADERS if header not in resolved_header_map]
    if not missing:
        return []
    joined = ",".join(sorted(missing))
    return [f"docs/SOURCE_REGISTRY_STATUS.md:required_headers_missing:{joined}"]


def _validate_source_registry_keyset(
    yaml_keys: set[str],
    row_keys: set[str],
) -> list[str]:
    errors: list[str] = []
    if not row_keys:
        return errors

    missing = sorted(yaml_keys - row_keys)
    extra = sorted(row_keys - yaml_keys)
    if missing:
        errors.append(
            f"docs/SOURCE_REGISTRY_STATUS.md:missing_source_keys:{','.join(missing)}"
        )
    if extra:
        errors.append(
            f"docs/SOURCE_REGISTRY_STATUS.md:unknown_source_keys:{','.join(extra)}"
        )
    return errors


def _validate_source_registry_declared_count(text: str, expected_count: int) -> list[str]:
    errors: list[str] = []
    count_match = re.search(r"-\s*total_sources:\s*(\d+)", text)
    if not count_match:
        return errors

    documented_count = int(count_match.group(1))
    if documented_count != expected_count:
        errors.append(
            "docs/SOURCE_REGISTRY_STATUS.md:source_count_mismatch:"
            f"{documented_count}!={expected_count}"
        )
    return errors


def _validate_source_registry_status_doc(sources: list[dict], source_truth_by_key: dict[str, dict]) -> list[str]:
    errors: list[str] = []
    doc_path = REPO_ROOT / "docs" / "SOURCE_REGISTRY_STATUS.md"
    if not doc_path.exists():
        errors.append("docs/SOURCE_REGISTRY_STATUS.md:missing")
        return errors

    text = doc_path.read_text(encoding="utf-8", errors="ignore")
    yaml_keys = {str(source.get("source_key")) for source in sources}
    header_map = _extract_source_registry_header_map(text)
    resolved_header_map = _resolve_source_registry_headers(header_map)
    row_keys, row_cells_by_key = _parse_source_registry_rows(text)

    errors.extend(_validate_source_registry_headers(resolved_header_map))
    errors.extend(_validate_source_registry_keyset(yaml_keys=yaml_keys, row_keys=row_keys))
    errors.extend(_validate_source_registry_declared_count(text, len(sources)))

    if not errors:
        for source_key in sorted(row_keys & set(source_truth_by_key.keys())):
            errors.extend(
                _validate_source_registry_row(
                    source_key=source_key,
                    cells=row_cells_by_key.get(source_key, []),
                    truth=source_truth_by_key[source_key],
                    resolved_header_map=resolved_header_map,
                )
            )

    return errors


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []

    sources = _load_yaml_sources()
    truth_summary, truth_enable_ready_ids, truth_runnable_ids, truth_sources_by_key = _load_source_truth()
    sources_by_key = {str(source.get("source_key")): source for source in sources}

    adapter_files = {
        path.name
        for path in (REPO_ROOT / "backend" / "app" / "ingestion" / "source_adapters").glob("*.py")
    }

    doc_entries = _collect_doc_texts()
    for path, text in doc_entries:
        rel = path.relative_to(REPO_ROOT)

        if re.search(r"source_adapters/justice_laws_xml\.py", text):
            errors.append(f"{rel}:stale_adapter_path:source_adapters/justice_laws_xml.py")

        if re.search(r"source_adapters/justice_laws_pit_xml\.py", text):
            errors.append(f"{rel}:stale_adapter_path:source_adapters/justice_laws_pit_xml.py")

        if re.search(
            r"justice_canada_laws_pit_xml.*(implemented|adapter\s+exists:\s+yes|can\s+run\s+now:\s+yes|current\s+alpha\s+status:\s+runnable)",
            text,
            re.IGNORECASE,
        ):
            pit = sources_by_key.get("justice_canada_laws_pit_xml", {})
            if pit.get("automation_status") == "adapter_missing":
                errors.append(f"{rel}:pit_xml_claims_implemented_but_adapter_missing")

        if re.search(r"complete\s+canadian\s+coverage", text, re.IGNORECASE):
            errors.append(f"{rel}:forbidden_complete_coverage_claim")

    if "laws_justice_xml.py" not in adapter_files:
        errors.append("backend/app/ingestion/source_adapters/laws_justice_xml.py:missing")

    errors.extend(_validate_source_registry_status_doc(sources, truth_sources_by_key))
    errors.extend(
        _validate_governance_docs(
            summary_counts=truth_summary,
            enable_ready_ids=truth_enable_ready_ids,
            runnable_ids=truth_runnable_ids,
        )
    )

    if errors:
        print("SOURCE REGISTRY DOCS: FAIL")
        for err in errors:
            print(f"- {err}")
        return 1

    print("SOURCE REGISTRY DOCS: PASS")
    print(f"sources_checked={len(sources)}")
    for warning in warnings:
        print(f"warning={warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
