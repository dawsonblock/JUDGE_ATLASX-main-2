"""Pipeline coordinator — topological sort for multi-step job dependencies."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class PipelineStep:
    """A single step in a pipeline."""

    name: str
    job_name: str
    payload: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)
    priority: int = 5  # 1 = highest, 10 = lowest


@dataclass
class PipelinePlan:
    """Execution plan produced by :class:`PipelineCoordinator`."""

    steps: list[PipelineStep]  # topological execution order
    has_cycle: bool = False


class PipelineCoordinator:
    """Builds dependency-ordered execution plans for multi-step pipelines."""

    def plan(self, steps: list[PipelineStep]) -> PipelinePlan:
        """Topologically sort *steps* using Kahn's algorithm.

        Sets ``has_cycle = True`` when a dependency cycle is detected.
        Raises ``ValueError`` when a step lists an unknown dependency.
        """
        step_map: dict[str, PipelineStep] = {s.name: s for s in steps}

        # Validate all dependency references.
        for step in steps:
            for dep in step.depends_on:
                if dep not in step_map:
                    raise ValueError(
                        f"Step {step.name!r} depends on unknown step {dep!r}"
                    )

        # Build adjacency: dep_name → list of step names that depend on it.
        dependents: dict[str, list[str]] = {s.name: [] for s in steps}
        in_degree: dict[str, int] = {s.name: 0 for s in steps}

        for step in steps:
            for dep in step.depends_on:
                dependents[dep].append(step.name)
                in_degree[step.name] += 1

        # Start with steps that have no prerequisites, sorted by priority.
        queue: list[str] = sorted(
            [name for name, deg in in_degree.items() if deg == 0],
            key=lambda n: (step_map[n].priority, n),
        )

        order: list[str] = []
        while queue:
            current = queue.pop(0)
            order.append(current)
            newly_ready = []
            for dep_name in dependents[current]:
                in_degree[dep_name] -= 1
                if in_degree[dep_name] == 0:
                    newly_ready.append(dep_name)
            # Insert newly-ready steps and re-sort by priority.
            queue.extend(newly_ready)
            queue.sort(key=lambda n: (step_map[n].priority, n))

        has_cycle = len(order) != len(steps)
        ordered_steps = [step_map[name] for name in order]
        if has_cycle:
            # Fallback to submission order so callers still get a plan object.
            ordered_steps = list(steps)

        return PipelinePlan(steps=ordered_steps, has_cycle=has_cycle)

    def ready_steps(
        self,
        plan: PipelinePlan,
        completed: set[str],
    ) -> list[PipelineStep]:
        """Return steps whose every dependency appears in *completed*."""
        return [
            s
            for s in plan.steps
            if s.name not in completed and all(d in completed for d in s.depends_on)
        ]

    def is_complete(self, plan: PipelinePlan, completed: set[str]) -> bool:
        """Return ``True`` when every step in *plan* is in *completed*."""
        return all(s.name in completed for s in plan.steps)
