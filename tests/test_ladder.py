"""Ladder stage assessment.

Stage 1 compares reproductive output against a random-action baseline, so the
statistic has to stay a rate when an arm dies.
"""

from __future__ import annotations

from worldzero.core.config import SimulationConfig
from worldzero.detectors.base import Criterion, DetectionResult
from worldzero.detectors.ladder import assess_stage_1, build_ladder
from worldzero.results import RunResult


def _run(label: str, *, births: int, population: float, founders: int = 200) -> RunResult:
    config = SimulationConfig(name="t").merged({"cell": {"start_population": founders}})
    return RunResult(
        run_id=f"{label}-{births}",
        world_id="w",
        label=label,
        seed=1,
        config=config,
        steps=1000,
        final_stats={"births": births, "population": population},
        metric_summary={"final": {"population": population}},
        extinct_at=None if population else 1000,
    )


def test_extinct_arm_does_not_inflate_births_per_capita() -> None:
    """An arm that died must not outscore a living one on a per-capita rate."""
    living = [_run("treatment", births=1000, population=150.0) for _ in range(3)]
    extinct = [_run("random", births=400, population=0.0) for _ in range(3)]

    result = assess_stage_1(living, extinct)
    outbreeds = next(c for c in result.criteria if c.name == "outbreeds_random_baseline")

    assert outbreeds.passed, outbreeds.detail
    assert outbreeds.value > 0


def test_births_per_capita_is_a_rate_not_a_total() -> None:
    few = [_run("treatment", births=200, population=100.0, founders=200)]
    many = [_run("random", births=200, population=100.0, founders=50)]

    result = assess_stage_1(few, many)
    outbreeds = next(c for c in result.criteria if c.name == "outbreeds_random_baseline")

    # Same births, but the arm with fewer founders achieved more per founder.
    assert not outbreeds.passed


def test_missing_runs_report_unavailable() -> None:
    assert not assess_stage_1([], []).detected


def test_ladder_requires_contiguity() -> None:
    detections = [
        DetectionResult.from_criteria("self_maintenance", 0, [Criterion("a", True, "")]),
        DetectionResult.from_criteria("resource_behaviour", 1, [Criterion("a", False, "")]),
        DetectionResult.from_criteria("memory", 2, [Criterion("a", True, "")]),
    ]

    ladder = build_ladder(detections)

    # Stage 2 reached but stage 1 missing: a gap is more likely measurement
    # error than a leapfrog, so the contiguous figure stops at 0.
    assert ladder.highest_contiguous == 0
    assert ladder.highest_any == 2
