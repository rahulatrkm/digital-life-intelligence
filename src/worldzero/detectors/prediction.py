"""Prediction detector (whitepaper section 14.2).

    Evidence for prediction :=
      action at time t correlates with environmental state at t+k AND
      future state is not visible at t AND
      anticipatory action improves survival vs reactive baseline

The middle clause is the one that is easy to fake. It is enforced structurally
rather than statistically: the detector refuses to run unless the environment is
one where the payoff is genuinely invisible at decision time -- a cue-lead
resource or hazard regime with a non-zero lead time.
"""

from __future__ import annotations

from worldzero.detectors.base import Criterion, DetectionResult, Detector
from worldzero.metrics.information import normalised_mutual_information
from worldzero.results import RunResult

ANTICIPATORY_REGIMES = {"hidden", "cyclic", "moving_front"}
ANTICIPATORY_HAZARDS = {"delayed", "spreading", "predator"}
MI_THRESHOLD = 0.02


class PredictionDetector(Detector):
    name = "prediction"
    stage = 3
    required_controls = ("no_memory",)

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

        reactive = controls["no_memory"]
        criteria: list[Criterion] = []

        criteria.append(self._future_is_hidden(treatment))
        criteria.append(self._acts_before_state_arrives(treatment))

        criterion, test = self.beats_control_criterion(
            "beats_reactive_baseline", treatment, reactive, seed=23
        )
        criteria.append(criterion)

        return DetectionResult.from_criteria(
            self.name,
            self.stage,
            criteria,
            evidence={
                "test": test.to_dict(),
                "cue_action_mi": round(self.mean(treatment, "cue_action_mi"), 6),
            },
        )

    @staticmethod
    def _future_is_hidden(treatment: list[RunResult]) -> Criterion:
        config = treatment[0].config
        resource_ok = (
            config.resources.regime in ANTICIPATORY_REGIMES
            and config.resources.cue_lead_time > 0
        )
        hazard_ok = (
            config.hazards.regime in ANTICIPATORY_HAZARDS and config.hazards.cue_lead_time > 0
        )
        ok = resource_ok or hazard_ok
        return Criterion(
            "future_state_not_visible",
            ok,
            f"resources={config.resources.regime}, hazards={config.hazards.regime}; "
            "prediction is only meaningful under a cue-lead regime",
        )

    def _acts_before_state_arrives(self, treatment: list[RunResult]) -> Criterion:
        """I(action_t ; resource at the same tile at t+k) across several lags."""
        best_overall = 0.0
        best_lag = 0
        for run in treatment:
            if run.trace is None or not run.trace.samples:
                continue
            lead = max(1, run.config.resources.cue_lead_time)
            for lag in (lead // 2, lead, lead * 2):
                if lag <= 0:
                    continue
                actions, futures = run.trace.future_resource(lag)
                if actions.size < 50:
                    continue
                score = normalised_mutual_information(actions, futures)
                if score > best_overall:
                    best_overall, best_lag = score, lag
        if best_overall == 0.0:
            return Criterion("acts_before_future_state", False, "insufficient paired samples")
        return Criterion(
            "acts_before_future_state",
            best_overall > MI_THRESHOLD,
            f"max normalised I(action_t; resource_t+k) = {best_overall:.4f} at k={best_lag}",
            best_overall,
        )
