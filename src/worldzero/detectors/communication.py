"""Communication and cooperation detectors (whitepaper sections 14.3 and 14.4)."""

from __future__ import annotations

import numpy as np

from worldzero.detectors.base import Criterion, DetectionResult, Detector
from worldzero.metrics.information import normalised_mutual_information
from worldzero.results import RunResult

SIGNAL_MI_THRESHOLD = 0.02
RECEIVER_MI_THRESHOLD = 0.02


class CommunicationDetector(Detector):
    """Whitepaper section 14.3.

        Evidence for communication :=
          emitted signal reduces uncertainty for receiver about
          resource/hazard/cell state AND
          receiver behavior changes in response to signal AND
          signal-scrambled control reduces fitness or coordination

    Signal *volume* is deliberately not evidence. Section 19 lists spammed
    signals as a named failure mode whose diagnostic is "high signal volume no
    information", so every criterion here is about mutual information or
    behaviour, never about emission counts.
    """

    name = "communication"
    stage = 4
    required_controls = ("scrambled_signals",)

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

        scrambled = controls["scrambled_signals"]
        criteria: list[Criterion] = []

        criteria.append(self._signals_are_informative(treatment))
        criteria.append(self._receivers_respond(treatment))

        criterion, test = self.beats_control_criterion(
            "beats_scrambled_signals", treatment, scrambled, seed=37
        )
        criteria.append(criterion)

        return DetectionResult.from_criteria(
            self.name,
            self.stage,
            criteria,
            evidence={
                "test": test.to_dict(),
                "signal_gene_fraction": round(self.mean(treatment, "signal_gene_fraction"), 6),
                "active_signals": round(self.mean(treatment, "active_signals"), 4),
            },
        )

    @staticmethod
    def _signals_are_informative(treatment: list[RunResult]) -> Criterion:
        scores: list[float] = []
        for run in treatment:
            if run.trace is None or not run.trace.samples:
                continue
            signals = run.trace.column("signal_here")
            if not signals.any():
                continue
            scores.append(
                max(
                    normalised_mutual_information(signals, run.trace.column("resource_here")),
                    normalised_mutual_information(signals, run.trace.column("hazard_here")),
                )
            )
        if not scores:
            return Criterion("signal_carries_information", False, "no signals observed")
        best = float(np.mean(scores))
        return Criterion(
            "signal_carries_information",
            best > SIGNAL_MI_THRESHOLD,
            f"mean normalised I(signal; environment) = {best:.4f}",
            best,
        )

    @staticmethod
    def _receivers_respond(treatment: list[RunResult]) -> Criterion:
        scores: list[float] = []
        for run in treatment:
            if run.trace is None or not run.trace.samples:
                continue
            signals = run.trace.column("signal_here")
            if not signals.any():
                continue
            scores.append(normalised_mutual_information(signals, run.trace.actions()))
        if not scores:
            return Criterion("receiver_behaviour_changes", False, "no signals observed")
        best = float(np.mean(scores))
        return Criterion(
            "receiver_behaviour_changes",
            best > RECEIVER_MI_THRESHOLD,
            f"mean normalised I(signal; action) = {best:.4f}",
            best,
        )


class CooperationDetector(Detector):
    """Whitepaper section 14.4.

        Evidence for cooperation :=
          group outcome > sum or average of isolated individual outcomes under
          matched resources AND
          behavior involves cost or constraint for at least one participant AND
          behavior persists across generations
    """

    name = "cooperation"
    stage = 5
    required_controls = ("isolated",)

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

        isolated = controls["isolated"]
        criteria: list[Criterion] = []

        criterion, test = self.beats_control_criterion(
            "groups_beat_isolated", treatment, isolated, seed=53
        )
        criteria.append(criterion)

        criteria.append(self._is_costly(treatment))
        criteria.append(self._persists_across_generations(treatment))

        return DetectionResult.from_criteria(
            self.name,
            self.stage,
            criteria,
            evidence={
                "test": test.to_dict(),
                "cooperation_index": round(self.mean(treatment, "cooperation_index"), 6),
            },
        )

    @staticmethod
    def _is_costly(treatment: list[RunResult]) -> Criterion:
        """At least one participant must be paying something.

        Proximity alone is not cooperation -- cells crowding a food patch look
        social and are not. Signalling and tile modification are the two actions
        that cost the actor and benefit whoever comes next.
        """
        costly = 0.0
        for run in treatment:
            costly += run.metric("active_signals") + run.metric("total_marker")
        mean = costly / len(treatment)
        return Criterion(
            "involves_cost_to_participant",
            mean > 0.0,
            f"mean costly-act intensity (signals + markers) = {mean:.4f}",
            mean,
        )

    @staticmethod
    def _persists_across_generations(treatment: list[RunResult]) -> Criterion:
        indices = [r.metric("cooperation_index") for r in treatment]
        generations = [r.metric("max_generation") for r in treatment]
        if not indices:
            return Criterion("persists_across_generations", False, "no data")
        mean_index = float(np.mean(indices))
        mean_generation = float(np.mean(generations))
        ok = mean_index > 0.0 and mean_generation >= 5
        return Criterion(
            "persists_across_generations",
            ok,
            f"cooperation index {mean_index:.4f} over {mean_generation:.1f} generations",
            mean_index,
        )
