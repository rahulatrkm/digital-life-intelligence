"""Culture and scientific-behaviour detectors (whitepaper sections 14.6 and 14.7)."""

from __future__ import annotations

import numpy as np

from worldzero.detectors.base import Criterion, DetectionResult, Detector
from worldzero.metrics.information import normalised_mutual_information
from worldzero.results import RunResult

MARKER_MI_THRESHOLD = 0.02


class CultureDetector(Detector):
    """Whitepaper section 14.6.

        Evidence for culture :=
          information persists after original cell death AND
          later cells use it to improve survival, prediction, or coordination AND
          removing the external memory/signaling layer reduces performance

    The first clause is what separates culture from memory: the marker layer
    decays roughly a thousand times slower than a signal, so information written
    onto the world routinely outlives the cell that wrote it.
    """

    name = "culture"
    stage = 7
    required_controls = ("no_markers",)

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

        stripped = controls["no_markers"]
        criteria: list[Criterion] = []

        criteria.append(self._information_outlives_authors(treatment))
        criteria.append(self._later_cells_use_it(treatment))

        criterion, test = self.beats_control_criterion(
            "removing_layer_reduces_performance", treatment, stripped, seed=71
        )
        criteria.append(criterion)

        return DetectionResult.from_criteria(
            self.name,
            self.stage,
            criteria,
            evidence={
                "test": test.to_dict(),
                "total_marker": round(self.mean(treatment, "total_marker"), 4),
            },
        )

    @staticmethod
    def _information_outlives_authors(treatment: list[RunResult]) -> Criterion:
        """Marker persistence must exceed a typical lifetime to count."""
        ratios: list[float] = []
        for run in treatment:
            markers = run.series_values("total_marker")
            lifespan = run.metric("mean_lifespan")
            if not markers or lifespan <= 0:
                continue
            decay = run.config.physics.marker_decay
            if decay >= 1.0:
                half_life = float("inf")
            elif decay <= 0.0:
                half_life = 0.0
            else:
                half_life = float(np.log(0.5) / np.log(decay))
            if max(markers) <= 0.0:
                continue
            ratios.append(half_life / lifespan)
        if not ratios:
            return Criterion("information_persists_after_death", False, "no markers written")
        ratio = float(np.mean(ratios))
        return Criterion(
            "information_persists_after_death",
            ratio > 1.0,
            f"marker half-life is {ratio:.2f}x the mean lifespan",
            ratio,
        )

    @staticmethod
    def _later_cells_use_it(treatment: list[RunResult]) -> Criterion:
        scores: list[float] = []
        for run in treatment:
            if run.trace is None or not run.trace.samples:
                continue
            markers = run.trace.column("marker_here")
            if not markers.any():
                continue
            scores.append(normalised_mutual_information(markers, run.trace.actions()))
        if not scores:
            return Criterion("descendants_use_information", False, "no marker observations")
        best = float(np.mean(scores))
        return Criterion(
            "descendants_use_information",
            best > MARKER_MI_THRESHOLD,
            f"mean normalised I(marker; action) = {best:.4f}",
            best,
        )


class ScienceDetector(Detector):
    """Whitepaper section 14.7.

        Evidence for scientific behavior :=
          cell performs costly intervention that is not immediately
          reward-maximizing AND
          intervention changes future information state AND
          resulting information improves later action, lineage survival, or
          group capability

    PROBE is the intervention: it costs energy, returns no energy, and its only
    effect is to move otherwise-unobservable state into a register.
    """

    name = "scientific_behaviour"
    stage = 8
    required_controls = ("no_probe",)

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

        no_probe = controls["no_probe"]
        criteria: list[Criterion] = []

        gain = self.mean(treatment, "probe_info_gain")
        criteria.append(
            Criterion(
                "performs_costly_intervention",
                gain > 0.0,
                f"mean cumulative probe information gain = {gain:.4f} "
                f"at {treatment[0].config.physics.probe_cost} energy per probe",
                gain,
            )
        )
        criteria.append(self._changes_information_state(treatment))

        criterion, test = self.beats_control_criterion(
            "information_improves_outcomes", treatment, no_probe, seed=89
        )
        criteria.append(criterion)

        return DetectionResult.from_criteria(
            self.name,
            self.stage,
            criteria,
            evidence={"test": test.to_dict(), "probe_info_gain": round(gain, 6)},
        )

    @staticmethod
    def _changes_information_state(treatment: list[RunResult]) -> Criterion:
        """Probed information must actually vary; a constant register informs nothing."""
        variances: list[float] = []
        for run in treatment:
            if run.trace is None or not run.trace.samples:
                continue
            memory = run.trace.memory_matrix()
            if memory.size and memory.shape[1]:
                variances.append(float(memory.var()))
        if not variances:
            return Criterion("changes_future_information_state", False, "no register observations")
        variance = float(np.mean(variances))
        return Criterion(
            "changes_future_information_state",
            variance > 1e-6,
            f"mean register variance after probing = {variance:.6f}",
            variance,
        )
