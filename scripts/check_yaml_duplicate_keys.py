#!/usr/bin/env python3
"""Fail on duplicate YAML mapping keys in source registry files.

Scans backend/app/ingestion/sources/*.yaml and reports duplicates with file,
key, and line number. Exits non-zero on any duplicate key.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import yaml
except Exception as exc:  # pragma: no cover
    print(f"ERROR: PyYAML is required: {exc}")
    sys.exit(2)


class DuplicateKeyError(Exception):
    def __init__(self, file_path: Path, key: str, line: int):
        super().__init__(f"{file_path}:{line}: duplicate key '{key}'")
        self.file_path = file_path
        self.key = key
        self.line = line


class UniqueKeyLoader(yaml.SafeLoader):
    pass


def _construct_mapping(loader: yaml.SafeLoader, node, deep=False):
    mapping = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise DuplicateKeyError(
                file_path=Path(getattr(loader.stream, "name", "<unknown>")),
                key=str(key),
                line=key_node.start_mark.line + 1,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def _scan_yaml(path: Path) -> list[DuplicateKeyError]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            yaml.load(handle, Loader=UniqueKeyLoader)
        return []
    except DuplicateKeyError as err:
        return [err]
    except yaml.YAMLError as err:
        print(f"ERROR: failed to parse {path}: {err}")
        return [DuplicateKeyError(path, "<parse_error>", 1)]


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    sources_dir = repo_root / "backend" / "app" / "ingestion" / "sources"

    yaml_paths = sorted(sources_dir.glob("*.yaml"))
    if not yaml_paths:
        print(f"ERROR: no YAML files found in {sources_dir}")
        return 2

    errors: list[DuplicateKeyError] = []
    for yaml_path in yaml_paths:
        errors.extend(_scan_yaml(yaml_path))

    if errors:
        print("FAIL: duplicate YAML keys detected")
        for err in errors:
            print(f"- file: {err.file_path}")
            print(f"  key: {err.key}")
            print(f"  line: {err.line}")
        return 1

    print(f"PASS: no duplicate YAML keys in {len(yaml_paths)} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
