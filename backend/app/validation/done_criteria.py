"""Done criteria validation (Phase 24).

Validates that all phases are complete and project is ready.
"""

import logging
from typing import Dict, Any, List
from pathlib import Path

logger = logging.getLogger(__name__)


class DoneCriteriaValidator:
    """Validates completion of all project phases."""

    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.phases = [
            "phase1",
            "phase2",
            "phase3",
            "phase4",
            "phase5",
            "phase6",
            "phase7",
            "phase8",
            "phase9",
            "phase10",
            "phase11",
            "phase12",
            "phase13",
            "phase14",
            "phase15",
            "phase16",
            "phase17",
            "phase18",
            "phase19",
            "phase20",
            "phase21",
            "phase22",
            "phase23",
            "phase24",
        ]

    def check_phase_completion(self) -> Dict[str, Any]:
        """Check completion status of all phases.

        Returns:
            Phase completion status
        """
        completed = []
        pending = []

        for phase in self.phases:
            # Check if phase has implementation files
            phase_files = self._find_phase_files(phase)
            if phase_files:
                completed.append(phase)
            else:
                pending.append(phase)

        return {
            "total_phases": len(self.phases),
            "completed": len(completed),
            "pending": len(pending),
            "completed_phases": completed,
            "pending_phases": pending,
            "completion_percentage": (len(completed) / len(self.phases)) * 100,
        }

    def _find_phase_files(self, phase: str) -> List[str]:
        """Find implementation files for a phase.

        Args:
            phase: Phase identifier

        Returns:
            List of file paths
        """
        files = []

        # Check backend implementation files
        backend_dir = self.project_root / "backend" / "app"
        if backend_dir.exists():
            # Look for phase-specific modules
            for py_file in backend_dir.rglob("*.py"):
                if phase.replace("phase", "phase_") in py_file.name.lower():
                    files.append(str(py_file))

        # Check test files
        tests_dir = backend_dir / "tests"
        if tests_dir.exists():
            for test_file in tests_dir.rglob("test_*.py"):
                if phase.replace("phase", "phase_") in test_file.name.lower():
                    files.append(str(test_file))

        return files

    def check_test_coverage(self) -> Dict[str, Any]:
        """Check that all phases have test coverage.

        Returns:
            Test coverage status
        """
        phases_with_tests = []
        phases_without_tests = []

        for phase in self.phases:
            test_files = self._find_phase_test_files(phase)
            if test_files:
                phases_with_tests.append(phase)
            else:
                phases_without_tests.append(phase)

        return {
            "phases_with_tests": len(phases_with_tests),
            "phases_without_tests": len(phases_without_tests),
            "missing_tests": phases_without_tests,
            "test_coverage_percentage": (
                (len(phases_with_tests) / len(self.phases)) * 100
            ),
        }

    def _find_phase_test_files(self, phase: str) -> List[str]:
        """Find test files for a phase.

        Args:
            phase: Phase identifier

        Returns:
            List of test file paths
        """
        test_files = []
        tests_dir = self.project_root / "backend" / "app" / "tests"

        if tests_dir.exists():
            for test_file in tests_dir.glob(f"test_{phase.replace('phase', 'phase_')}*.py"):
                test_files.append(str(test_file))

        return test_files

    def validate_done_criteria(self) -> Dict[str, Any]:
        """Validate all done criteria.

        Returns:
            Done criteria validation result
        """
        phase_status = self.check_phase_completion()
        test_status = self.check_test_coverage()

        all_phases_complete = phase_status["completion_percentage"] == 100
        all_phases_tested = test_status["test_coverage_percentage"] == 100

        is_done = all_phases_complete and all_phases_tested

        return {
            "all_phases_complete": all_phases_complete,
            "all_phases_tested": all_phases_tested,
            "is_done": is_done,
            "phase_completion": phase_status,
            "test_coverage": test_status,
            "ready_for_release": is_done,
        }


def validate_done_criteria(project_root: str = ".") -> Dict[str, Any]:
    """Validate done criteria for the project.

    Args:
        project_root: Project root directory

    Returns:
        Done criteria validation result
    """
    validator = DoneCriteriaValidator(project_root)
    return validator.validate_done_criteria()
