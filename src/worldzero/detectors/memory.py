"""Memory detector (whitepaper section 14.1).

    Evidence for memory :=
      behavior depends on internal_state or past observation AND
      memory-enabled lineages outperform memory-scrambled controls AND
      effect persists across multiple seeds and environments

The scrambled control matters more than the disabled one. Removing registers
changes the genome's search space; scrambling them leaves the architecture
identical and destroys only the *content*, which isolates whether what was
stored was doing any work.
"""

from __future__ import annotations

import numpy as np

from worldzero.detectors.base import Criterion, DetectionResult, Detector
from worldzero.metrics.information import normalised_mutual_information
from worldzero.results import RunResult

MI_THRESHOLD = 0.02


class MemoryDetector(Detector):
    name = "memory"
    stage = 2
    required_controls = ("scrambled_memory",)

    def detect(
        self,
        treatment: list[RunResult],
        controls: dict[str, list[RunResult]],
    ) -> DetectionResult:
        if not treatment:
            return self.unavailable("no treatment runs")
        missing = self.missing_controls(controls)
        if missing:
            return self.unavailable(f"missing controls: {', '.join(missing)}")

        scrambled = controls["scrambled_memory"]
        criteria: list[Criterion] = []

        dependence = self._behaviour_depends_on_memory(treatment)
        criteria.append(dependence)

        criterion, test = self.beats_control_criterion(
            "beats_scrambled_memory", treatment, scrambled, seed=11
        )
        criteria.append(criterion)

        criteria.append(self.consistent_across_seeds(treatment, scrambled))

        return DetectionResult.from_criteria(
            self.name,
            self.stage,
            criteria,
            evidence={
                "treatment_fitness": round(float(np.mean(self.fitness_array(treatment))), 6),
                "scrambled_fitness": round(float(np.mean(self.fitness_array(scrambled))), 6),
                "test": test.to_dict(),
                "memory_gene_fraction": round(self.mean(treatment, "memory_gene_fraction"), 6),
            },
        )

    def _behaviour_depends_on_memory(self, treatment: list[RunResult]) -> Criterion:
        """Mutual information between a register's value and the action taken."""
        scores: list[float] = []
        for run in treatment:
            if run.trace is None or not run.trace.samples:
                continue
            memory = run.trace.memory_matrix()
            if not memory.size or memory.shape[1] == 0:
                continue
            actions = run.trace.actions()
            scores.append(
                max(
                    normalised_mutual_information(memory[:, i], actions)
                    for i in range(memory.shape[1])
                )
            )
        if not scores:
            return Criterion("behaviour_depends_on_memory", False, "no usable traces")
        best = float(np.mean(scores))
        return Criterion(
            "behaviour_depends_on_memory",
            best > MI_THRESHOLD,
            f"mean normalised I(memory; action) = {best:.4f} (threshold {MI_THRESHOLD})",
            best,
        )
