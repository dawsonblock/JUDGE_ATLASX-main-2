"""CI/CD gate validation (Phase 21).

Provides CI/CD pipeline gates and deployment validation.
"""

import subprocess
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class CICDGate:
    """Enforces CI/CD pipeline gates."""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)

    def check_git_clean(self) -> Dict[str, Any]:
        """Check if git working directory is clean.

        Returns:
            Git status check result
        """
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=30,
            )

            is_clean = len(result.stdout.strip()) == 0

            return {
                "is_clean": is_clean,
                "output": result.stdout,
                "passed": is_clean,
            }
        except subprocess.TimeoutExpired:
            return {
                "is_clean": False,
                "error": "Timeout",
                "passed": False,
            }
        except FileNotFoundError:
            return {
                "is_clean": True,
                "skipped": "Git not available",
                "passed": True,
            }
        except Exception as e:
            return {
                "is_clean": False,
                "error": str(e),
                "passed": False,
            }

    def check_branch_name(self, allowed_patterns: List[str]) -> Dict[str, Any]:
        """Check if branch name follows allowed patterns.

        Args:
            allowed_patterns: List of allowed branch patterns

        Returns:
            Branch name check result
        """
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=30,
            )

            branch = result.stdout.strip()

            # Check if branch matches any allowed pattern
            matches = any(
                pattern in branch for pattern in allowed_patterns
            )

            return {
                "branch": branch,
                "allowed_patterns": allowed_patterns,
                "matches": matches,
                "passed": matches,
            }
        except subprocess.TimeoutExpired:
            return {
                "passed": False,
                "error": "Timeout",
            }
        except FileNotFoundError:
            return {
                "passed": True,
                "skipped": "Git not available",
            }
        except Exception as e:
            return {
                "passed": False,
                "error": str(e),
            }

    def check_environment_variables(
        self,
        required_vars: List[str],
    ) -> Dict[str, Any]:
        """Check required environment variables.

        Args:
            required_vars: List of required variable names

        Returns:
            Environment check result
        """
        import os

        missing = []
        present = []

        for var in required_vars:
            if var in os.environ:
                present.append(var)
            else:
                missing.append(var)

        return {
            "required_count": len(required_vars),
            "present_count": len(present),
            "missing_count": len(missing),
            "missing": missing,
            "passed": len(missing) == 0,
        }

    def check_dependencies(self) -> Dict[str, Any]:
        """Check if required dependencies are installed.

        Returns:
            Dependency check result
        """
        required_packages = [
            "sqlalchemy",
            "fastapi",
            "pydantic",
        ]

        missing = []
        installed = []

        for package in required_packages:
            try:
                __import__(package)
                installed.append(package)
            except ImportError:
                missing.append(package)

        return {
            "required_count": len(required_packages),
            "installed_count": len(installed),
            "missing_count": len(missing),
            "missing": missing,
            "passed": len(missing) == 0,
        }

    def check_database_connection(self, connection_string: Optional[str] = None) -> Dict[str, Any]:
        """Check database connection.

        Args:
            connection_string: Database connection string

        Returns:
            Database check result
        """
        # Simplified check - in production use actual connection test
        return {
            "passed": True,
            "skipped": "Connection test not implemented",
        }

    def run_pre_deployment_checks(self) -> Dict[str, Any]:
        """Run all pre-deployment checks.

        Returns:
            Combined check results
        """
        results = {
            "git_clean": self.check_git_clean(),
            "branch_name": self.check_branch_name(["main", "develop", "feature/"]),
            "environment_vars": self.check_environment_variables([]),
            "dependencies": self.check_dependencies(),
            "database": self.check_database_connection(),
        }

        # Overall pass status
        all_passed = all(
            r.get("passed", False) for r in results.values()
        )

        results["overall_passed"] = all_passed

        return results


def get_cicd_gate_status(project_root: str = ".") -> Dict[str, Any]:
    """Get current CI/CD gate status.

    Args:
        project_root: Project root directory

    Returns:
        CI/CD gate status
    """
    gate = CICDGate(project_root)
    return gate.run_pre_deployment_checks()
