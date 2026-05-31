#!/usr/bin/env python3
"""Validate all source YAML workflow files in backend/app/ingestion/sources/.

Checks enforced:
  1.  All source_class values are in the canonical set
  2.  Every machine_ingest source has a parser field
  3.  Every machine_ingest parser is in ADAPTER_REGISTRY (when importable)
  4.  Every disabled_stub source has an admin_notes field
  5.  No source has enabled_default: true
  6.  Non-runnable source classes must not have auto_publish_enabled: true
  7.  source_key, source_name, source_class are present and non-empty
  8.  creates field is a parseable list (if present)
  9.  Cross-file source_key uniqueness
  10. Duplicate mapping keys within any single YAML file

Exit code: 0 if all checks pass, 1 if any violation is found.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
_SOURCES_DIR = _REPO_ROOT / "backend" / "app" / "ingestion" / "sources"

# Try to import ADAPTER_REGISTRY for parser-key validation.
# Import may fail in environments without optional C-extension dependencies
# (e.g. BeautifulSoup/lxml); in that case the check is silently skipped.
_ADAPTER_REGISTRY_KEYS: frozenset[str] | None = None
try:
    sys.path.insert(0, str(_REPO_ROOT / "backend"))
    from app.ingestion.source_adapters import ADAPTER_REGISTRY as _reg  # type: ignore[import]
    _ADAPTER_REGISTRY_KEYS = frozenset(_reg.keys())
except Exception:
    pass

_CANONICAL_CLASSES = frozenset(
    {
        "machine_ingest",
        "portal_reference",
        "disabled_stub",
        "manual_reference",
        "requires_api_key",
        "needs_endpoint_configuration",
    }
)

# Classes that must never have auto_publish_enabled: true
_NO_AUTO_PUBLISH = frozenset(
    {
        "portal_reference",
        "disabled_stub",
        "manual_reference",
        "requires_api_key",
        "needs_endpoint_configuration",
    }
)

_REQUIRED_FIELDS = ("source_key", "source_name", "source_class")


class UniqueKeyLoader(yaml.SafeLoader):
    """yaml.SafeLoader subclass that raises on duplicate mapping keys."""

    def construct_mapping(
        self, node: yaml.MappingNode, deep: bool = False
    ) -> dict:
        seen: list = []
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise yaml.constructor.ConstructorError(
                    "while constructing a mapping",
                    node.start_mark,
                    f"found duplicate key: {key!r}",
                    key_node.start_mark,
                )
            seen.append(key)
        return super().construct_mapping(node, deep=deep)


def _load_all_sources() -> list[dict]:
    """Load every source entry from every YAML file, detecting duplicate keys."""
    entries: list[dict] = []
    for path in sorted(_SOURCES_DIR.glob("*.yaml")):
        with path.open() as fh:
            try:
                # UniqueKeyLoader extends SafeLoader — safe for untrusted YAML
                data = yaml.load(fh, Loader=UniqueKeyLoader) or {}  # noqa: S506
            except yaml.YAMLError as exc:
                print(f"FAIL  YAML parse error in {path.name}:\n  {exc}")
                sys.exit(1)
        sources = data.get("sources") or data.get("source_list") or []
        if isinstance(sources, list):
            for s in sources:
                if isinstance(s, dict):
                    s["_file"] = path.name
                    entries.append(s)
    return entries


def main() -> int:
    yaml_files = list(_SOURCES_DIR.glob("*.yaml"))
    if not yaml_files:
        print(f"FAIL  No YAML files found in {_SOURCES_DIR}")
        return 1

    sources = _load_all_sources()
    if not sources:
        print(f"FAIL  No source entries loaded from {len(yaml_files)} file(s)")
        return 1

    violations: list[str] = []

    # 9. Cross-file source_key uniqueness
    seen_keys: dict[str, str] = {}
    for s in sources:
        sk = s.get("source_key")
        if sk:
            if sk in seen_keys:
                violations.append(
                    f"{sk}: duplicate source_key — appears in "
                    f"{seen_keys[sk]} and {s['_file']}"
                )
            else:
                seen_keys[sk] = s["_file"]

    for s in sources:
        key = s.get("source_key") or f"<unnamed in {s.get('_file')}>"
        sc = s.get("source_class")

        # 7. Required fields must be present and non-empty
        for field in _REQUIRED_FIELDS:
            if not s.get(field):
                violations.append(f"{key}: missing required field '{field}'")

        # 1. Canonical source_class
        if sc not in _CANONICAL_CLASSES:
            violations.append(
                f"{key}: unrecognised source_class {sc!r} "
                f"(not in {sorted(_CANONICAL_CLASSES)})"
            )

        # 2. machine_ingest must have parser
        if sc == "machine_ingest" and not s.get("parser"):
            violations.append(f"{key}: machine_ingest missing 'parser' field")

        # 3. machine_ingest parser must be in ADAPTER_REGISTRY (when importable)
        if sc == "machine_ingest" and s.get("parser") and _ADAPTER_REGISTRY_KEYS is not None:
            if s["parser"] not in _ADAPTER_REGISTRY_KEYS:
                violations.append(
                    f"{key}: parser {s['parser']!r} not in ADAPTER_REGISTRY "
                    f"(known: {sorted(_ADAPTER_REGISTRY_KEYS)})"
                )

        # 4. disabled_stub must have admin_notes
        if sc == "disabled_stub" and not s.get("admin_notes"):
            violations.append(f"{key}: disabled_stub missing 'admin_notes' field")

        # 5. enabled_default must not be True
        if s.get("enabled_default") is True:
            violations.append(
                f"{key}: enabled_default is True (sources must default to disabled)"
            )

        # 6. Non-runnable classes must not auto-publish
        if sc in _NO_AUTO_PUBLISH and s.get("auto_publish_enabled") is True:
            violations.append(f"{key}: {sc} must not have auto_publish_enabled: true")

        # 8. creates must be a parseable list
        creates_raw = s.get("creates")
        if creates_raw is not None:
            if isinstance(creates_raw, str):
                try:
                    parsed = json.loads(creates_raw)
                    if not isinstance(parsed, list):
                        raise ValueError("not a list")
                except (json.JSONDecodeError, ValueError):
                    violations.append(
                        f"{key}: 'creates' field is not a valid JSON list: {creates_raw!r}"
                    )
            elif not isinstance(creates_raw, list):
                violations.append(
                    f"{key}: 'creates' field must be a list or JSON list string"
                )

    if violations:
        print(f"FAIL  {len(violations)} violation(s) detected:\n")
        for v in violations:
            print(f"  - {v}")
        return 1

    n = len(sources)
    print(f"PASS  {n} source(s) across {len(yaml_files)} file(s) validated OK")
    if _ADAPTER_REGISTRY_KEYS is None:
        print(
            "NOTE  ADAPTER_REGISTRY unavailable (missing optional deps); "
            "parser key check skipped"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
