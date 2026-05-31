"""
Enforcement test: Verify that runtime code does NOT import from external_reference/.

This test parses all Python files in backend/app/ (excluding tests, legacy_disabled, 
external_reference) and checks for import statements that reference external_reference.

This boundary is critical for maintaining clean separation between:
- Production code (backend/app/, frontend/)
- Reference/archived code (external_reference/)
"""

import os
import re
from pathlib import Path

import pytest


def get_python_files(root_dir, exclude_dirs=None):
    """Recursively find all Python files in a directory."""
    if exclude_dirs is None:
        exclude_dirs = {"__pycache__", ".pytest_cache", "node_modules", ".venv"}
    
    python_files = []
    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Remove excluded directories from traversal
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs]
        
        for filename in filenames:
            if filename.endswith(".py"):
                python_files.append(os.path.join(dirpath, filename))
    
    return python_files


def check_import_statements(file_path):
    """Check if a Python file imports from external_reference."""
    violations = []
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except (UnicodeDecodeError, IOError):
        return violations
    
    # Patterns to detect imports from external_reference
    patterns = [
        r"^\s*from\s+external_reference",
        r"^\s*import\s+external_reference",
        r"^\s*from\s+\.\.\s+import",  # Relative imports from parent (could go up to external_reference)
    ]
    
    for line_num, line in enumerate(lines, 1):
        for pattern in patterns:
            if re.match(pattern, line):
                # Exclude false positives: comment lines
                if not line.strip().startswith("#"):
                    violations.append((line_num, line.strip()))
    
    return violations


def test_no_external_reference_imports_in_backend():
    """
    ENFORCEMENT: backend/app must NOT import from external_reference.
    
    This gate ensures that production code remains cleanly separated
    from archived/reference materials.
    """
    backend_root = Path(__file__).parent.parent.parent  # backend/app/
    
    # Find all Python files
    python_files = get_python_files(
        str(backend_root),
        exclude_dirs={
            "__pycache__",
            ".pytest_cache",
            "tests",
            ".venv",
            "venv",
            "site-packages",
            "node_modules",
        },
    )
    
    violations_by_file = {}
    
    for file_path in python_files:
        violations = check_import_statements(file_path)
        if violations:
            violations_by_file[file_path] = violations
    
    # Report violations
    assert not violations_by_file, (
        f"BOUNDARY VIOLATION: Runtime code imports from external_reference/:\n"
        + "\n".join(
            f"{file_path}:\n"
            + "\n".join(f"  Line {line_num}: {line}" for line_num, line in violations)
            for file_path, violations in violations_by_file.items()
        )
    )


def test_external_reference_directory_isolated():
    """
    ENFORCEMENT: external_reference/ should exist and be isolated.
    
    This gate ensures external_reference directory is present and
    not accidentally imported by runtime code.
    """
    repo_root = Path(__file__).resolve().parents[3]  # repository root
    external_ref_dir = repo_root / "external_reference"
    
    assert external_ref_dir.exists(), (
        f"external_reference/ directory not found at {external_ref_dir}. "
        "All non-runtime code should be in external_reference/."
    )
    
    # Verify subdirectories exist
    expected_subdirs = [
        "external_repos",
        "legacy_disabled",
        "archived_research",
    ]
    
    for subdir in expected_subdirs:
        assert (external_ref_dir / subdir).exists(), (
            f"Expected external_reference/{subdir}/ to exist"
        )
