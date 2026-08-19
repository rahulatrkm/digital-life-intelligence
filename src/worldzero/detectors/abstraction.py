"""Abstraction detector (whitepaper section 14.5).

    Evidence for abstraction :=
      same internal state or action policy generalizes across multiple
      surface-different but functionally related stimuli AND
      lineage handles unseen variants better than memorization baseline

Operationalised through resource variants: identical energy yield, different
surface signature. A lineage that keyed on the particular signatures it met
collapses on the rest; a lineage that abstracted "cue means food" does not.
"""

from __future__ import annotations

import numpy as np

from worldzero.detectors.base import Criterion, DetectionResult, Detector
from worldzero.results import RunResult

SPREAD_THRESHOLD = 0.25


class AbstractionDetector(Detector):
    name = "abstraction"
    stage = 6
    required_controls = ("single_variant",)

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

        memoriser = controls["single_variant"]
        criteria: list[Criterion] = []

        variants = treatment[0].config.resources.variants
        criteria.append(
            Criterion(
                "multiple_surface_variants",
                variants > 1,
                f"resources.variants = {variants}; abstraction needs >= 2 signatures",
                float(variants),
            )
        )
        criteria.append(self._generalises(treatment))

        criterion, test = self.beats_control_criterion(
            "beats_memorisation_baseline", treatment, memoriser, seed=61
        )
        criteria.append(criterion)

        return DetectionResult.from_criteria(
            self.name,
            self.stage,
            criteria,
            evidence={"test": test.to_dict(), "variants": variants},
        )

    @staticmethod
    def _generalises(treatment: list[RunResult]) -> Criterion:
        """Outcome should not depend on which signature the food happens to carry.

        Spread across signatures is the signal, not the mean: a memoriser does
        well on familiar signatures and badly on the rest, which shows up as high
        variance even when the average looks respectable.
        """
        spreads: list[float] = []
        for run in treatment:
            if run.trace is None or not run.trace.samples:
                continue
            cues = run.trace.column("cue_here")
            energies = run.trace.column("energy")
            if cues.size < 50 or np.allclose(cues, cues[0]):
                continue
            buckets: dict[int, list[float]] = {}
            for cue, energy in zip(np.round(cues, 1), energies, strict=False):
                buckets.setdefault(int(cue * 10), []).append(energy)
            means = [float(np.mean(v)) for v in buckets.values() if len(v) >= 5]
            if len(means) < 2:
                continue
            overall = abs(float(np.mean(means))) or 1.0
            spreads.append(float(np.std(means)) / overall)

        if not spreads:
            return Criterion("generalises_across_variants", False, "insufficient variant coverage")
        spread = float(np.mean(spreads))
        return Criterion(
            "generalises_across_variants",
            spread < SPREAD_THRESHOLD,
            f"relative spread of outcome across signatures = {spread:.4f} "
            f"(want < {SPREAD_THRESHOLD})",
            spread,
        )
