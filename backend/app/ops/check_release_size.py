"""Release size validation script.

Checks that release packages do not include:
- Archived research materials
- Forbidden folders
- Exceed size limits
"""

import sys
from pathlib import Path


# Forbidden folders that must not be in release
FORBIDDEN_FOLDERS = [
    "docs/reference/archived",
    "docs/reference/vendor_repos",
    "docs/reference/experiments",
    "external_reference",
    "research",
    "external",
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".next",
]

# Maximum release size in bytes (500 MB)
MAX_RELEASE_SIZE = 500 * 1024 * 1024


def check_release_size(directory: str = ".") -> bool:
    """Check if directory meets release size requirements.

    Args:
        directory: Root directory to check

    Returns:
        True if release is valid, False otherwise
    """
    root_path = Path(directory).resolve()
    issues = []

    # Check for forbidden folders
    for forbidden in FORBIDDEN_FOLDERS:
        forbidden_path = root_path / forbidden
        if forbidden_path.exists():
            issues.append(f"Forbidden folder found: {forbidden}")

    # Calculate total size
    total_size = 0
    for item in root_path.rglob("*"):
        if item.is_file() and not is_ignored(item, root_path):
            try:
                total_size += item.stat().st_size
            except OSError:
                pass

    # Check size limit
    if total_size > MAX_RELEASE_SIZE:
        size_mb = total_size / (1024 * 1024)
        max_mb = MAX_RELEASE_SIZE / (1024 * 1024)
        issues.append(
            f"Release size {size_mb:.2f} MB exceeds limit of {max_mb:.2f} MB"
        )

    # Report issues
    if issues:
        print("Release validation FAILED:")
        for issue in issues:
            print(f"  - {issue}")
        return False
    else:
        size_mb = total_size / (1024 * 1024)
        print(f"Release validation PASSED (size: {size_mb:.2f} MB)")
        return True


def is_ignored(file_path: Path, root_path: Path) -> bool:
    """Check if file should be ignored in size calculation.

    Args:
        file_path: File path to check
        root_path: Root directory

    Returns:
        True if file should be ignored
    """
    relative_path = file_path.relative_to(root_path)

    # Ignore common build artifacts
    ignored_patterns = [
        ".git",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".next",
        ".DS_Store",
        "*.pyc",
        "*.pyo",
        "*.egg-info",
    ]

    for pattern in ignored_patterns:
        if pattern in str(relative_path) or relative_path.match(pattern):
            return True

    return False


if __name__ == "__main__":
    directory = sys.argv[1] if len(sys.argv) > 1 else "."
    success = check_release_size(directory)
    sys.exit(0 if success else 1)
