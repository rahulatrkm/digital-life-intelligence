"""Emergence detectors (whitepaper section 14).

Every detector is conservative by construction: it reports a list of named
criteria and only claims detection when all of them pass. Detectors also declare
which controls they require and refuse to return a result without them, so a
missing ablation surfaces as "unavailable" rather than as a false positive.
"""

from __future__ import annotations

from worldzero.detectors.abstraction import AbstractionDetector
from worldzero.detectors.base import Criterion, DetectionResult, Detector
from worldzero.detectors.communication import CommunicationDetector, CooperationDetector
from worldzero.detectors.culture import CultureDetector, ScienceDetector
from worldzero.detectors.ladder import (
    STAGE_NAMES,
    LadderAssessment,
    assess_stage_0,
    assess_stage_1,
    assess_stage_9,
    assess_stage_10,
    build_ladder,
)
from worldzero.detectors.memory import MemoryDetector
from worldzero.detectors.prediction import PredictionDetector
from worldzero.results import RunResult

#: Ordered so that a run only reaches a detector once the mechanisms it
#: presupposes have been checked (section 21: "memory and prediction detectors
#: implemented before communication").
ALL_DETECTORS: tuple[type[Detector], ...] = (
    MemoryDetector,
    PredictionDetector,
    CommunicationDetector,
    CooperationDetector,
    AbstractionDetector,
    CultureDetector,
    ScienceDetector,
)

__all__ = [
    "ALL_DETECTORS",
    "STAGE_NAMES",
    "AbstractionDetector",
    "CommunicationDetector",
    "CooperationDetector",
    "Criterion",
    "CultureDetector",
    "DetectionResult",
    "Detector",
    "LadderAssessment",
    "MemoryDetector",
    "PredictionDetector",
    "ScienceDetector",
    "assess_stage_0",
    "assess_stage_1",
    "assess_stage_9",
    "assess_stage_10",
    "build_ladder",
    "run_all_detectors",
]


def run_all_detectors(
    treatment: list[RunResult],
    controls: dict[str, list[RunResult]],
) -> list[DetectionResult]:
    """Run every section 14 detector plus the ladder's directly-measured stages."""
    results: list[DetectionResult] = []

    random_control = controls.get("random", [])
    results.append(assess_stage_0(treatment, random_control))
    results.append(assess_stage_1(treatment, random_control))

    for detector_class in ALL_DETECTORS:
        results.append(detector_class().detect(treatment, controls))

    results.append(assess_stage_9(treatment))
    results.append(assess_stage_10(treatment))
    return results
