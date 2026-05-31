from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
RUNTIME_GLOBS = (
    "backend/app/**/*.py",
    "frontend/**/*.ts",
    "frontend/**/*.tsx",
    "frontend/**/*.js",
    "frontend/**/*.jsx",
)


def _python_imports_external(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    offenders: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "external" or alias.name.startswith("external."):
                    offenders.append(f"{path}:{node.lineno}")
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "external" or module.startswith("external."):
                offenders.append(f"{path}:{node.lineno}")
    return offenders


def test_runtime_code_does_not_import_external_reference_tree() -> None:
    offenders: list[str] = []
    for pattern in RUNTIME_GLOBS:
        for path in ROOT.glob(pattern):
            path_text = path.as_posix()
            if (
                not path.is_file()
                or "docs/" in path_text
                or "scripts/" in path_text
                or "/node_modules/" in path_text
                or "/.next/" in path_text
            ):
                continue
            if path.suffix == ".py":
                offenders.extend(_python_imports_external(path))
            else:
                text = path.read_text(encoding="utf-8")
                for idx, line in enumerate(text.splitlines(), start=1):
                    if "from 'external" in line or 'from "external' in line:
                        offenders.append(f"{path}:{idx}")
                    if "from '../external" in line or 'from "../external' in line:
                        offenders.append(f"{path}:{idx}")
    assert offenders == []
