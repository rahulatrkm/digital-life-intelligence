"""Experiment verdict semantics.

Stages 0 and 1 are measured for every experiment so the ladder has a base, but
an experiment must not be judged on a capability it was never designed to
elicit: E0 tests viability (section 16.1), resource seeking is E1's job.
"""

from __future__ import annotations

from worldzero.detectors.base import Criterion, DetectionResult
from worldzero.experiments.runner import ExperimentReport


def _detection(name: str, stage: int, passed: bool) -> DetectionResult:
    return DetectionResult.from_criteria(
        name, stage, [Criterion("dummy", passed, "synthetic criterion")]
    )


def test_verdict_ignores_undeclared_detectors() -> None:
    report = ExperimentReport(
        experiment_id="E0",
        name="Viability",
        goal="",
        detections=[
            _detection("self_maintenance", 0, True),
            _detection("resource_behaviour", 1, False),
        ],
        required=("self_maintenance",),
    )

    assert report.passed
    assert report.to_dict()["required_detectors"] == ["self_maintenance"]


def test_verdict_fails_when_a_declared_detector_fails() -> None:
    report = ExperimentReport(
        experiment_id="E1",
        name="Resource seeking",
        goal="",
        detections=[
            _detection("self_maintenance", 0, True),
            _detection("resource_behaviour", 1, False),
        ],
        required=("resource_behaviour",),
    )

    assert not report.passed


def test_undeclared_failures_are_marked_not_applicable() -> None:
    report = ExperimentReport(
        experiment_id="E0",
        name="Viability",
        goal="",
        detections=[
            _detection("self_maintenance", 0, True),
            _detection("resource_behaviour", 1, False),
        ],
        required=("self_maintenance",),
    )
    lines = "\n".join(report.summary_lines())

    assert "[PASS] stage  0 self_maintenance" in lines
    assert "[n/a ] stage  1 resource_behaviour" in lines


def test_verdict_falls_back_to_every_detector_when_none_declared() -> None:
    report = ExperimentReport(
        experiment_id="EX",
        name="Unscoped",
        goal="",
        detections=[_detection("self_maintenance", 0, True), _detection("memory", 2, False)],
    )

    assert not report.passed


def test_report_without_detections_does_not_pass() -> None:
    assert not ExperimentReport(experiment_id="EX", name="Empty", goal="").passed
