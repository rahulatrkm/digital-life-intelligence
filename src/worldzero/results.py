"""Run results.

Shared by the experiment runner (which produces them) and the detectors (which
consume them). Lives at package root so neither has to import the other.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from worldzero.core.config import SimulationConfig
    from worldzero.metrics.traces import BehaviorTrace


@dataclass
class RunResult:
    """Everything one world produced, in a form detectors can compare."""

    run_id: str
    world_id: str
    label: str
    seed: int
    config: SimulationConfig
    steps: int
    final_stats: dict[str, Any] = field(default_factory=dict)
    metric_summary: dict[str, Any] = field(default_factory=dict)
    metric_series: list[dict[str, Any]] = field(default_factory=list)
    lineage_summary: dict[str, Any] = field(default_factory=dict)
    acceleration: dict[str, Any] = field(default_factory=dict)
    events_path: str | None = None
    trace: BehaviorTrace | None = None
    extinct_at: int | None = None
    wallclock_seconds: float = 0.0

    # -- fitness views --------------------------------------------------------

    @property
    def final_metrics(self) -> dict[str, float]:
        return self.metric_summary.get("final", {})

    def metric(self, name: str, default: float = 0.0) -> float:
        value = self.final_metrics.get(name)
        if value is None:
            value = self.final_stats.get(name, default)
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def fitness(self) -> float:
        """Single scalar for control comparisons.

        Mean lifespan alone rewards a stagnant population that never breeds, and
        population alone rewards a boom-bust swarm. The product of the two,
        normalised by run length, penalises both failure modes.
        """
        lifespan = self.metric("mean_lifespan")
        population = self.metric("population")
        if self.extinct_at is not None:
            return 0.0
        return lifespan * max(1.0, population) / max(1.0, float(self.steps))

    def survived(self) -> bool:
        return self.extinct_at is None and self.metric("population") > 0

    def series_values(self, name: str) -> list[float]:
        out: list[float] = []
        for row in self.metric_series:
            value = row.get(name)
            if value is not None:
                out.append(float(value))
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "world_id": self.world_id,
            "label": self.label,
            "seed": self.seed,
            "steps": self.steps,
            "config_fingerprint": self.config.fingerprint(),
            "controls": self.config.controls.active(),
            "final_stats": self.final_stats,
            "metric_summary": self.metric_summary,
            "lineage_summary": self.lineage_summary,
            "acceleration": self.acceleration,
            "events_path": self.events_path,
            "extinct_at": self.extinct_at,
            "fitness": round(self.fitness(), 6),
            "wallclock_seconds": round(self.wallclock_seconds, 3),
        }
