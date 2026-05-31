"""Boundary tests: memory modules must not import public-facing map/graph routes."""

import ast
import importlib
from pathlib import Path

MEMORY_MODULES = [
    "app.memory",
    "app.memory.extract_claims",
    "app.memory.invalidation",
    "app.memory.rebuild",
    "app.memory.retrieval",
]

FORBIDDEN_IMPORTS = {
    "app.api.routes.map_record",
    "app.api.routes.public_events",
    "app.api.routes.graph",
    "app.models.map_record",
}


def _collect_imports(module_name: str) -> set[str]:
    """Return the set of module names imported by *module_name*."""
    mod = importlib.import_module(module_name)
    source_file = getattr(mod, "__file__", None)
    if not source_file:
        return set()
    tree = ast.parse(Path(source_file).read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imports.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module)
    return imports


class TestPublicBoundary:
    def test_no_forbidden_imports_in_memory_modules(self):
        for mod_name in MEMORY_MODULES:
            violations = _collect_imports(mod_name) & FORBIDDEN_IMPORTS
            assert (
                not violations
            ), f"{mod_name} imports forbidden public-route modules: {violations}"

    def test_memory_module_is_importable(self):
        """Smoke test: all memory modules can be imported without error."""
        for mod_name in MEMORY_MODULES:
            try:
                importlib.import_module(mod_name)
            except ImportError as exc:
                raise AssertionError(f"Failed to import {mod_name}: {exc}") from exc
