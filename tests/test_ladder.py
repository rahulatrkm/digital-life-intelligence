"""Ladder stage assessment.

Stage 1 compares reproductive output against a random-action baseline, so the
statistic has to stay a rate when an arm dies.
"""

from __future__ import annotations

from worldzero.core.config import SimulationConfig
from worldzero.detectors.base import Criterion, DetectionResult
from worldzero.detectors.ladder import assess_stage_0, assess_stage_1, build_ladder
from worldzero.results import RunResult


def _run(
    label: str,
    *,
    births: int,
    population: float,
    founders: int = 200,
    efficiency: float = 1.0,
) -> RunResult:
    config = SimulationConfig(name="t").merged({"cell": {"start_population": founders}})
    return RunResult(
        run_id=f"{label}-{births}",
        world_id="w",
        label=label,
        seed=1,
        config=config,
        steps=1000,
        final_stats={"births": births, "population": population},
        metric_summary={
            "final": {"population": population, "harvest_efficiency": efficiency}
        },
        extinct_at=None if population else 1000,
    )


def test_efficient_forager_is_not_penalised_for_eating() -> None:
    """The previous measure counted time standing on tiles that still had food,
    so a cell that ate the tile scored as though it had never found it."""
    good = [_run("treatment", births=1000, population=150.0, efficiency=2.0) for _ in range(3)]
    poor = [_run("random", births=400, population=150.0, efficiency=0.5) for _ in range(3)]

    result = assess_stage_1(good, poor)
    forages = next(c for c in result.criteria if c.name == "forages_more_efficiently")

    assert forages.passed, forages.detail
    assert result.detected


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


def _survival_run(
    label: str, *, lifespan: float, extinct_at: int | None, steps: int = 4000
) -> RunResult:
    return RunResult(
        run_id=f"{label}-{lifespan}",
        world_id="w",
        label=label,
        seed=1,
        config=SimulationConfig(name="t"),
        steps=steps,
        final_stats={"births": 100, "population": 0.0 if extinct_at else 150.0},
        metric_summary={
            "final": {
                "mean_lifespan": lifespan,
                "population": 0.0 if extinct_at else 150.0,
            }
        },
        extinct_at=extinct_at,
    )


def test_extinct_arm_cannot_outlast_a_surviving_one() -> None:
    """mean_lifespan averages only over cells that died, so a prolific lineage
    looks short-lived and a dying one looks long-lived. In E3/E4/E8 an extinct
    random arm scored ~112 against a thriving treatment's 42-53."""
    thriving = [_survival_run("treatment", lifespan=45.0, extinct_at=None) for _ in range(3)]
    dead = [_survival_run("random", lifespan=112.0, extinct_at=400) for _ in range(3)]

    result = assess_stage_0(thriving, dead)
    outlasts = next(c for c in result.criteria if c.name == "outlasts_random_baseline")

    assert outlasts.passed, outlasts.detail
    assert result.detected


def test_lifespan_breaks_the_tie_when_both_arms_survive() -> None:
    better = [_survival_run("treatment", lifespan=90.0, extinct_at=None) for _ in range(3)]
    worse = [_survival_run("random", lifespan=60.0, extinct_at=None) for _ in range(3)]

    assert assess_stage_0(better, worse).detected
    assert not assess_stage_0(worse, better).detected


def test_a_dying_treatment_does_not_pass_stage_0() -> None:
    dying = [_survival_run("treatment", lifespan=200.0, extinct_at=300) for _ in range(3)]
    surviving = [_survival_run("random", lifespan=50.0, extinct_at=None) for _ in range(3)]

    assert not assess_stage_0(dying, surviving).detected


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
