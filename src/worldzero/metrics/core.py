"""Metric engine (whitepaper section 15).

Metrics are computed on a schedule and appended to a series so that *rates* --
adaptation rate, complexity growth, intelligence acceleration -- can be derived
after the fact. A single end-of-run snapshot cannot express any of them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import numpy as np

from worldzero.metrics.information import normalised_mutual_information
from worldzero.metrics.novelty import NoveltyArchive, behaviour_signature, policy_entropy

if TYPE_CHECKING:  # pragma: no cover
    from worldzero.core.world import World
    from worldzero.metrics.traces import BehaviorTrace


@dataclass
class MetricSnapshot:
    timestep: int
    values: dict[str, float]

    def to_dict(self) -> dict[str, Any]:
        return {"timestep": self.timestep, **self.values}


@dataclass
class MetricEngine:
    """Whitepaper section 15.1."""

    novelty: NoveltyArchive = field(default_factory=NoveltyArchive)
    series: list[MetricSnapshot] = field(default_factory=list)
    _shock_baseline: float | None = field(default=None, repr=False)
    _recovery_times: list[int] = field(default_factory=list, repr=False)

    def compute(self, world: World, trace: BehaviorTrace | None = None) -> MetricSnapshot:
        cells = world.living_cells()
        lineage = world.lineage

        signature = behaviour_signature(cells)
        generation = lineage.max_generation()
        novelty_distance = self.novelty.observe(signature, generation)
        self.novelty.prune(generation)

        genome_lengths = [float(len(c.genome)) for c in cells]
        registers = [float(len(c.internal_state)) for c in cells]
        memory_users = sum(1 for c in cells if c.genome.uses_memory())
        signal_users = sum(1 for c in cells if c.genome.uses_signals())

        values: dict[str, float] = {
            # population and survival
            "population": float(len(cells)),
            "births": float(world.births),
            "deaths": float(world.deaths),
            "mean_lifespan": lineage.mean_lifespan(),
            "median_lifespan": lineage.median_lifespan(),
            "mean_energy": float(np.mean([c.energy for c in cells])) if cells else 0.0,
            # reproductive fitness
            "surviving_lineages": float(len(lineage.surviving_lineages)),
            "max_generation": float(generation),
            "mean_offspring": _mean_offspring(lineage),
            # complexity growth
            "mean_genome_length": float(np.mean(genome_lengths)) if genome_lengths else 0.0,
            "mean_registers": float(np.mean(registers)) if registers else 0.0,
            "distinct_genomes": float(len({c.genome.hash for c in cells})),
            "policy_entropy": policy_entropy(cells),
            "memory_gene_fraction": (memory_users / len(cells)) if cells else 0.0,
            "signal_gene_fraction": (signal_users / len(cells)) if cells else 0.0,
            # novelty
            "novelty_distance": 0.0 if novelty_distance == float("inf") else novelty_distance,
            "novelty_archive": float(len(self.novelty.archive)),
            # ecology
            "total_resource": float(world.resource.sum()),
            "total_hazard": float(world.hazard.sum()),
            "total_marker": float(world.marker.sum()),
            "active_signals": float(len(world.signals)),
            "probe_info_gain": float(world.probe_info_gain),
            "energy_balance": world.ledger.balance(world.living_energy()),
        }

        values["adaptation_rate"] = self._adaptation_rate(world, values["population"])
        if trace is not None:
            values.update(self._trace_metrics(trace))

        snapshot = MetricSnapshot(timestep=world.timestep, values=values)
        self.series.append(snapshot)
        return snapshot

    # -- derived quantities ---------------------------------------------------

    def _adaptation_rate(self, world: World, population: float) -> float:
        """Steps to recover the pre-shock population after an environmental shift.

        Reported as a rate (1/steps) so that larger is better and a run with no
        shocks scores 0 rather than infinity.
        """
        if not world.shocks:
            return 0.0
        latest = world.shocks[-1]
        if self._shock_baseline is None or latest > getattr(self, "_last_shock", -1):
            self._last_shock = latest
            self._shock_baseline = population
            return 0.0
        if self._shock_baseline and population >= self._shock_baseline:
            elapsed = max(1, world.timestep - latest)
            self._recovery_times.append(elapsed)
            self._shock_baseline = None
            return 1.0 / elapsed
        return 0.0

    def _trace_metrics(self, trace: BehaviorTrace) -> dict[str, float]:
        if not trace.samples:
            return {}
        actions = trace.actions()
        out: dict[str, float] = {}

        memory = trace.memory_matrix()
        if memory.size and memory.shape[1]:
            out["memory_action_mi"] = max(
                normalised_mutual_information(memory[:, i], actions)
                for i in range(memory.shape[1])
            )
            out["memory_variance"] = float(memory.var())

        signals = trace.column("signal_here")
        if signals.any():
            out["signal_resource_mi"] = normalised_mutual_information(
                signals, trace.column("resource_here")
            )
            out["signal_hazard_mi"] = normalised_mutual_information(
                signals, trace.column("hazard_here")
            )

        cues = trace.column("cue_here")
        if cues.any():
            out["cue_action_mi"] = normalised_mutual_information(cues, actions)

        out["cooperation_index"] = float(np.corrcoef(
            trace.column("neighbours"), trace.column("energy")
        )[0, 1]) if len(trace.samples) > 2 else 0.0
        if np.isnan(out["cooperation_index"]):
            out["cooperation_index"] = 0.0
        return out

    # -- reporting ------------------------------------------------------------

    def intelligence_acceleration_rate(self, capability_key: str = "novelty_archive") -> float:
        """Section 15.1: capability growth divided by simulation time.

        Reported as the *change* in growth rate between the first and second
        half of the run, since section 21 asks whether the growth rate itself
        increases -- a constant rate of new behaviour is not acceleration.
        """
        if len(self.series) < 4:
            return 0.0
        values = [s.values.get(capability_key, 0.0) for s in self.series]
        steps = [s.timestep for s in self.series]
        mid = len(values) // 2
        first = _slope(steps[:mid], values[:mid])
        second = _slope(steps[mid:], values[mid:])
        return float(second - first)

    def latest(self) -> MetricSnapshot | None:
        return self.series[-1] if self.series else None

    def to_rows(self) -> list[dict[str, Any]]:
        return [s.to_dict() for s in self.series]

    def summary(self) -> dict[str, Any]:
        latest = self.latest()
        return {
            "snapshots": len(self.series),
            "novelty": self.novelty.summary(),
            "mean_recovery_steps": (
                float(np.mean(self._recovery_times)) if self._recovery_times else 0.0
            ),
            "intelligence_acceleration_rate": self.intelligence_acceleration_rate(),
            "final": latest.values if latest else {},
        }


def _slope(x: list[int], y: list[float]) -> float:
    if len(x) < 2:
        return 0.0
    xs = np.asarray(x, dtype=np.float64)
    ys = np.asarray(y, dtype=np.float64)
    span = xs.var()
    if span <= 0:
        return 0.0
    return float(((xs - xs.mean()) * (ys - ys.mean())).mean() / span)


def _mean_offspring(lineage) -> float:
    stats = [s for s in lineage.lineages.values() if s.deaths]
    if not stats:
        return 0.0
    return float(np.mean([s.mean_offspring for s in stats]))
