"""Detector base types (whitepaper section 14).

"The detector should be conservative: a behavior counts only if it persists,
improves fitness, and survives controls." That sentence is implemented literally
here -- a detector reports a list of named criteria, and ``detected`` is the
conjunction of all of them. A detector that fires on two of three criteria is a
negative result with useful diagnostics, not a partial success.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from worldzero.metrics.information import TestResult, permutation_test
from worldzero.results import RunResult


@dataclass
class Criterion:
    name: str
    passed: bool
    detail: str = ""
    value: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
            "value": None if self.value is None else round(self.value, 6),
        }


@dataclass
class DetectionResult:
    name: str
    stage: int
    detected: bool
    confidence: float
    criteria: list[Criterion] = field(default_factory=list)
    evidence: dict[str, Any] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "detector": self.name,
            "stage": self.stage,
            "detected": self.detected,
            "confidence": round(self.confidence, 6),
            "criteria": [c.to_dict() for c in self.criteria],
            "evidence": self.evidence,
            "notes": self.notes,
        }

    @classmethod
    def from_criteria(
        cls,
        name: str,
        stage: int,
        criteria: list[Criterion],
        evidence: dict[str, Any] | None = None,
        notes: list[str] | None = None,
    ) -> DetectionResult:
        passed = [c for c in criteria if c.passed]
        return cls(
            name=name,
            stage=stage,
            detected=len(passed) == len(criteria) and bool(criteria),
            confidence=len(passed) / len(criteria) if criteria else 0.0,
            criteria=criteria,
            evidence=evidence or {},
            notes=notes or [],
        )


class Detector:
    """Base class. Subclasses implement :meth:`detect`."""

    name: str = "base"
    stage: int = 0
    required_controls: tuple[str, ...] = ()

    def detect(
        self,
        treatment: list[RunResult],
        controls: dict[str, list[RunResult]],
    ) -> DetectionResult:
        raise NotImplementedError

    # -- shared helpers -------------------------------------------------------

    def missing_controls(self, controls: dict[str, list[RunResult]]) -> list[str]:
        return [name for name in self.required_controls if not controls.get(name)]

    def unavailable(self, reason: str) -> DetectionResult:
        return DetectionResult(
            name=self.name,
            stage=self.stage,
            detected=False,
            confidence=0.0,
            criteria=[Criterion("preconditions", False, reason)],
            notes=[reason],
        )

    @staticmethod
    def fitness_array(runs: list[RunResult]) -> np.ndarray:
        return np.asarray([r.fitness() for r in runs], dtype=np.float64)

    @staticmethod
    def metric_array(runs: list[RunResult], name: str) -> np.ndarray:
        return np.asarray([r.metric(name) for r in runs], dtype=np.float64)

    def beats_control(
        self,
        treatment: list[RunResult],
        control: list[RunResult],
        *,
        seed: int = 0,
    ) -> TestResult:
        return permutation_test(
            self.fitness_array(treatment),
            self.fitness_array(control),
            seed=seed,
        )

    def beats_control_criterion(
        self,
        name: str,
        treatment: list[RunResult],
        control: list[RunResult],
        *,
        seed: int = 0,
    ) -> tuple[Criterion, TestResult]:
        """Compare fitness against a control, reporting power separately.

        A permutation test cannot return a p below 1/(number of labellings), so
        at 3 versus 3 runs significance is unreachable however large the effect.
        Reporting that as a plain failure would claim the mechanism was absent
        when the design simply could not see it, so it is called out the way a
        missing control is: as a precondition, not as evidence.
        """
        test = self.beats_control(treatment, control, seed=seed)
        if test.underpowered:
            detail = (
                f"underpowered: {test.n_treatment}v{test.n_control} runs can reach "
                f"p>={test.resolution:.3f} at best; need more seeds "
                f"(delta {test.statistic:.4f}, d={test.effect_size:.3f})"
            )
            return Criterion(name, False, detail, test.statistic), test

        return (
            Criterion(
                name,
                test.statistic > 0 and test.significant,
                f"fitness delta {test.statistic:.4f}, p={test.p_value:.4f}, "
                f"d={test.effect_size:.3f}",
                test.statistic,
            ),
            test,
        )

    @staticmethod
    def consistent_across_seeds(
        treatment: list[RunResult],
        control: list[RunResult],
        minimum_seeds: int = 3,
    ) -> Criterion:
        """Whitepaper 14.1: the effect must persist across multiple seeds.

        Checks the sign of the per-seed difference rather than the aggregate, so
        one runaway seed cannot carry a result that the others contradict.
        """
        if len(treatment) < minimum_seeds or len(control) < minimum_seeds:
            return Criterion(
                "persists_across_seeds",
                False,
                f"need >= {minimum_seeds} seeds per arm, "
                f"have {len(treatment)} treatment / {len(control)} control",
            )
        control_mean = float(np.mean([r.fitness() for r in control]))
        wins = sum(1 for r in treatment if r.fitness() > control_mean)
        fraction = wins / len(treatment)
        return Criterion(
            "persists_across_seeds",
            fraction >= 0.75,
            f"{wins}/{len(treatment)} seeds beat the control mean",
            fraction,
        )

    @staticmethod
    def mean(runs: list[RunResult], name: str) -> float:
        values = [r.metric(name) for r in runs]
        return float(np.mean(values)) if values else 0.0
