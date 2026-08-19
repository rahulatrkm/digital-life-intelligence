"""The emergence ladder (whitepaper section 9).

Stages 0 and 1 are measured directly against baselines rather than by a
detector, because "cells persist longer than random motion" and "movement
becomes resource-directed" are population statistics, not mechanisms. Stages 2
through 8 come from the section 14 detectors. Stages 9 and 10 are derived from
long-run novelty and from whether the capability growth *rate* increased.

The ladder is reported as the highest stage reached with no gaps below it: a
communication result with no memory result underneath is far more likely to be
a measurement artefact than a leapfrog.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from worldzero.detectors.base import Criterion, DetectionResult
from worldzero.results import RunResult

STAGE_NAMES: dict[int, str] = {
    0: "self-maintenance",
    1: "resource behaviour",
    2: "memory",
    3: "prediction",
    4: "communication",
    5: "cooperation",
    6: "abstraction",
    7: "culture",
    8: "scientific behaviour",
    9: "civilization",
    10: "intelligence acceleration",
}


@dataclass
class LadderAssessment:
    stages: dict[int, bool] = field(default_factory=dict)
    highest_contiguous: int = -1
    highest_any: int = -1
    details: dict[int, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "highest_contiguous_stage": self.highest_contiguous,
            "highest_contiguous_name": STAGE_NAMES.get(self.highest_contiguous, "none"),
            "highest_any_stage": self.highest_any,
            "stages": {
                str(stage): {
                    "name": STAGE_NAMES[stage],
                    "reached": reached,
                    **self.details.get(stage, {}),
                }
                for stage, reached in sorted(self.stages.items())
            },
        }


def assess_stage_0(treatment: list[RunResult], random_control: list[RunResult]) -> DetectionResult:
    """Cells persist longer than a random-motion baseline."""
    if not treatment or not random_control:
        return DetectionResult("self_maintenance", 0, False, 0.0, notes=["missing runs"])

    evolved = float(np.mean([r.metric("mean_lifespan") for r in treatment]))
    random_lifespan = float(np.mean([r.metric("mean_lifespan") for r in random_control]))
    survived = sum(1 for r in treatment if r.survived())

    criteria = [
        Criterion(
            "outlives_random_baseline",
            evolved > random_lifespan,
            f"mean lifespan {evolved:.2f} vs random {random_lifespan:.2f}",
            evolved - random_lifespan,
        ),
        Criterion(
            "population_does_not_collapse",
            survived >= max(1, len(treatment) // 2),
            f"{survived}/{len(treatment)} runs still populated at the end",
            float(survived),
        ),
    ]
    return DetectionResult.from_criteria("self_maintenance", 0, criteria)


def assess_stage_1(treatment: list[RunResult], random_control: list[RunResult]) -> DetectionResult:
    """Movement becomes resource-directed rather than arbitrary."""
    if not treatment or not random_control:
        return DetectionResult("resource_behaviour", 1, False, 0.0, notes=["missing runs"])

    def harvest_per_capita(runs: list[RunResult]) -> float:
        values = []
        for run in runs:
            population = max(1.0, run.metric("population"))
            values.append(run.final_stats.get("births", 0) / population)
        return float(np.mean(values)) if values else 0.0

    evolved = harvest_per_capita(treatment)
    random_rate = harvest_per_capita(random_control)

    occupancy = []
    for run in treatment:
        if run.trace is None or not run.trace.samples:
            continue
        occupancy.append(float(np.mean(run.trace.column("resource_here") > 0.0)))
    random_occupancy = []
    for run in random_control:
        if run.trace is None or not run.trace.samples:
            continue
        random_occupancy.append(float(np.mean(run.trace.column("resource_here") > 0.0)))

    criteria = [
        Criterion(
            "outbreeds_random_baseline",
            evolved > random_rate,
            f"births per capita {evolved:.3f} vs random {random_rate:.3f}",
            evolved - random_rate,
        ),
        Criterion(
            "occupies_resource_tiles",
            bool(occupancy)
            and bool(random_occupancy)
            and float(np.mean(occupancy)) > float(np.mean(random_occupancy)),
            f"time on resource tiles {np.mean(occupancy) if occupancy else 0:.3f} "
            f"vs random {np.mean(random_occupancy) if random_occupancy else 0:.3f}",
        ),
    ]
    return DetectionResult.from_criteria("resource_behaviour", 1, criteria)


def assess_stage_9(treatment: list[RunResult]) -> DetectionResult:
    """Persistent structures accumulate: novelty keeps arriving and does not collapse."""
    if not treatment:
        return DetectionResult("civilization", 9, False, 0.0, notes=["missing runs"])

    archives = [r.metric("novelty_archive") for r in treatment]
    markers = [r.metric("total_marker") for r in treatment]
    growth = []
    for run in treatment:
        series = run.series_values("novelty_archive")
        if len(series) >= 4:
            half = len(series) // 2
            growth.append(series[-1] - series[half])

    criteria = [
        Criterion(
            "persistent_novelty",
            bool(growth) and float(np.mean(growth)) > 0,
            f"novelty archive grew by {np.mean(growth) if growth else 0:.2f} in the second half",
        ),
        Criterion(
            "persistent_structures",
            float(np.mean(markers)) > 0,
            f"mean persistent marker mass {np.mean(markers):.3f}",
        ),
        Criterion(
            "accumulated_repertoire",
            float(np.mean(archives)) >= 3,
            f"mean archive size {np.mean(archives):.2f}",
        ),
    ]
    return DetectionResult.from_criteria("civilization", 9, criteria)


def assess_stage_10(treatment: list[RunResult]) -> DetectionResult:
    """Capability growth rate itself increases (whitepaper section 15.1, IAR)."""
    if not treatment:
        return DetectionResult("intelligence_acceleration", 10, False, 0.0, notes=["missing runs"])

    rates = [
        float(r.metric_summary.get("intelligence_acceleration_rate", 0.0)) for r in treatment
    ]
    mean_rate = float(np.mean(rates)) if rates else 0.0
    positive = sum(1 for r in rates if r > 0)

    criteria = [
        Criterion(
            "growth_rate_increases",
            mean_rate > 0,
            f"mean IAR (second-half slope minus first-half slope) = {mean_rate:.6f}",
            mean_rate,
        ),
        Criterion(
            "consistent_across_seeds",
            len(rates) >= 3 and positive >= 0.75 * len(rates),
            f"{positive}/{len(rates)} seeds show positive acceleration",
        ),
    ]
    return DetectionResult.from_criteria("intelligence_acceleration", 10, criteria)


def build_ladder(results: list[DetectionResult]) -> LadderAssessment:
    assessment = LadderAssessment()
    by_stage: dict[int, DetectionResult] = {}
    for result in results:
        existing = by_stage.get(result.stage)
        if existing is None or result.confidence > existing.confidence:
            by_stage[result.stage] = result

    for stage in range(11):
        result = by_stage.get(stage)
        reached = bool(result and result.detected)
        assessment.stages[stage] = reached
        if result is not None:
            assessment.details[stage] = {
                "detector": result.name,
                "confidence": round(result.confidence, 4),
                "failed_criteria": [c.name for c in result.criteria if not c.passed],
            }
        if reached:
            assessment.highest_any = stage

    contiguous = -1
    for stage in range(11):
        if assessment.stages.get(stage):
            contiguous = stage
        else:
            break
    assessment.highest_contiguous = contiguous
    return assessment
