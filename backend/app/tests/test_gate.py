"""Test gate expansion (Phase 20).

Provides test coverage validation and quality gates.
"""

import subprocess
import logging
from typing import Dict, Any, List, Optional
from pathlib import Path

logger = logging.getLogger(__name__)


class TestGate:
    """Enforces test coverage and quality gates."""
    __test__ = False

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.min_coverage = 80.0
        self.required_test_files: List[str] = []

    def check_test_coverage(
        self,
        module: str,
        min_coverage: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Check test coverage for a module.

        Args:
            module: Module to check coverage for
            min_coverage: Minimum coverage threshold

        Returns:
            Coverage check result
        """
        threshold = min_coverage or self.min_coverage

        # Run coverage check
        try:
            result = subprocess.run(
                ["pytest", f"--cov={module}", "--cov-report=term-missing"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=300,
            )
            output = result.stdout + result.stderr

            # Parse coverage from output (simplified)
            coverage = self._parse_coverage(output)

            passed = coverage >= threshold

            return {
                "module": module,
                "coverage": coverage,
                "threshold": threshold,
                "passed": passed,
                "output": output,
            }
        except subprocess.TimeoutExpired:
            return {
                "module": module,
                "coverage": 0.0,
                "threshold": threshold,
                "passed": False,
                "error": "Timeout",
            }
        except Exception as e:
            return {
                "module": module,
                "coverage": 0.0,
                "threshold": threshold,
                "passed": False,
                "error": str(e),
            }

    def _parse_coverage(self, output: str) -> float:
        """Parse coverage percentage from pytest output.

        Args:
            output: pytest output string

        Returns:
            Coverage percentage
        """
        # Simplified parsing - in production use proper coverage tool
        for line in output.split("\n"):
            if "TOTAL" in line and "%" in line:
                try:
                    parts = line.split()
                    for part in parts:
                        if "%" in part:
                            return float(part.replace("%", ""))
                except (ValueError, IndexError):
                    pass
        return 0.0

    def check_required_tests(self) -> Dict[str, Any]:
        """Check that required test files exist.

        Returns:
            Test file check result
        """
        missing = []
        found = []

        for test_file in self.required_test_files:
            test_path = self.project_root / test_file
            if test_path.exists():
                found.append(test_file)
            else:
                missing.append(test_file)

        return {
            "required_count": len(self.required_test_files),
            "found_count": len(found),
            "missing_count": len(missing),
            "missing": missing,
            "passed": len(missing) == 0,
        }

    def run_test_suite(
        self,
        pattern: str = "test_*.py",
        verbose: bool = False,
    ) -> Dict[str, Any]:
        """Run the full test suite.

        Args:
            pattern: Test file pattern
            verbose: Enable verbose output

        Returns:
            Test suite result
        """
        cmd = ["pytest", pattern]
        if verbose:
            cmd.append("-v")

        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=600,
            )

            passed = result.returncode == 0

            return {
                "passed": passed,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
            }
        except subprocess.TimeoutExpired:
            return {
                "passed": False,
                "error": "Timeout",
            }
        except Exception as e:
            return {
                "passed": False,
                "error": str(e),
            }

    def check_linting(self) -> Dict[str, Any]:
        """Check code linting status.

        Returns:
            Linting check result
        """
        try:
            result = subprocess.run(
                ["ruff", "check", "."],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=120,
            )

            passed = result.returncode == 0

            return {
                "passed": passed,
                "returncode": result.returncode,
                "output": result.stdout + result.stderr,
            }
        except subprocess.TimeoutExpired:
            return {
                "passed": False,
                "error": "Timeout",
            }
        except FileNotFoundError:
            # Ruff not installed, skip
            return {
                "passed": True,
                "skipped": "Ruff not installed",
            }
        except Exception as e:
            return {
                "passed": False,
                "error": str(e),
            }

    def run_all_gates(self) -> Dict[str, Any]:
        """Run all test gates.

        Returns:
            Combined gate results
        """
        results = {
            "test_coverage": self.check_test_coverage("app"),
            "required_tests": self.check_required_tests(),
            "test_suite": self.run_test_suite(),
            "linting": self.check_linting(),
        }

        # Overall pass status
        all_passed = all(
            r.get("passed", False) for r in results.values()
        )

        results["overall_passed"] = all_passed

        return results


def get_test_gate_status(project_root: str = ".") -> Dict[str, Any]:
    """Get current test gate status.

    Args:
        project_root: Project root directory

    Returns:
        Test gate status
    """
    gate = TestGate(project_root)
    return gate.run_all_gates()
