"""Behaviour traces.

Detectors need a record of *what cells did and what the world then did*, which
neither the event log (too coarse when sampled) nor the final state (too late)
provides. Traces are sampled periodically rather than every step: section 15.2
cares about behaviour that persists, so a sparse sample over a long run carries
more signal than a dense sample over a short one.
"""

from __future__ import annotations

from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass, field
from math import inf
from typing import TYPE_CHECKING, Any

import numpy as np

from worldzero.core.types import ActionType

if TYPE_CHECKING:  # pragma: no cover
    from worldzero.core.world import World


@dataclass(slots=True)
class TraceSample:
    timestep: int
    cell_id: str
    lineage_id: str
    generation: int
    x: int
    y: int
    energy: float
    action: int
    resource_here: float
    hazard_here: float
    cue_here: float
    marker_here: float
    signal_here: float
    memory: tuple[float, ...]
    neighbours: int
    used_memory_gene: bool


@dataclass
class BehaviorTrace:
    """Ring-buffered samples plus the tile futures needed for lag analysis."""

    max_samples: int = 200_000
    max_cells_per_sample: int = 200
    samples: list[TraceSample] = field(default_factory=list)
    tile_future: dict[tuple[int, int, int], float] = field(default_factory=dict)
    signal_observations: list[tuple[float, float, float]] = field(default_factory=list)
    """(signal value, resource at emitter, hazard at emitter) for the
    communication detector's mutual-information estimate."""
    truncated: bool = False
    _index: dict[tuple[int, int], list[tuple[int, float]]] | None = field(
        default=None, repr=False
    )
    _interval: int | None = field(default=None, repr=False)

    def sample(self, world: World) -> None:
        if len(self.samples) >= self.max_samples:
            self.truncated = True
            return

        cells = world.living_cells()
        if not cells:
            return
        if len(cells) > self.max_cells_per_sample:
            rng = world.rng.local("trace", world.timestep)
            cells = rng.sample(cells, self.max_cells_per_sample)

        channels = world.signal_field.shape[0]
        for cell in cells:
            action = cell.last_action.type if cell.last_action else ActionType.STAY
            signal_here = (
                float(world.signal_field[:, cell.y, cell.x].sum()) if channels else 0.0
            )
            self.samples.append(
                TraceSample(
                    timestep=world.timestep,
                    cell_id=cell.id,
                    lineage_id=cell.lineage_id,
                    generation=cell.generation,
                    x=cell.x,
                    y=cell.y,
                    energy=cell.energy,
                    action=int(action),
                    resource_here=float(world.resource[cell.y, cell.x]),
                    hazard_here=float(world.hazard[cell.y, cell.x]),
                    cue_here=float(world.cue[cell.y, cell.x]),
                    marker_here=float(world.marker[cell.y, cell.x]),
                    signal_here=signal_here,
                    memory=tuple(cell.internal_state),
                    neighbours=self._neighbours(world, cell.x, cell.y),
                    used_memory_gene=cell.genome.uses_memory(),
                )
            )
            key = (world.timestep, cell.x, cell.y)
            self.tile_future[key] = float(world.resource[cell.y, cell.x])

    @staticmethod
    def _neighbours(world: World, x: int, y: int) -> int:
        count = 0
        for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            nx, ny = world.wrap(x + dx, y + dy)
            if nx >= 0 and (nx, ny) in world.occupancy:
                count += 1
        return count

    # -- views used by detectors ---------------------------------------------

    def actions(self) -> np.ndarray:
        return np.asarray([s.action for s in self.samples], dtype=np.int64)

    def column(self, name: str) -> np.ndarray:
        return np.asarray([getattr(s, name) for s in self.samples], dtype=np.float64)

    def memory_matrix(self) -> np.ndarray:
        if not self.samples:
            return np.zeros((0, 0))
        width = max(len(s.memory) for s in self.samples)
        matrix = np.zeros((len(self.samples), width), dtype=np.float64)
        for row, sample in enumerate(self.samples):
            if sample.memory:
                matrix[row, : len(sample.memory)] = sample.memory
        return matrix

    def future_resource(self, lag: int) -> tuple[np.ndarray, np.ndarray]:
        """Pair each sample's action with the resource at its tile ``lag`` steps later.

        Tiles are only recorded on sampling steps, so an exact lookup of
        ``timestep + lag`` finds nothing unless the lag happens to be a multiple
        of the sampling interval. The lags come from ``cue_lead_time``, which has
        no reason to line up: at trace_interval 20 and cue_lead_time 12 the
        detector tried lags 6, 12 and 24 and got exactly zero pairs every time,
        so the criterion could never fire whatever the population did.

        The nearest recorded observation at or after the target is used instead,
        within one sampling interval, which is the resolution the trace has.
        """
        index = self._tile_index()
        tolerance = max(1, self._sampling_interval())

        actions: list[int] = []
        futures: list[float] = []
        for sample in self.samples:
            history = index.get((sample.x, sample.y))
            if not history:
                continue
            target = sample.timestep + lag
            position = bisect_left(history, (target, -inf))
            if position >= len(history):
                continue
            when, value = history[position]
            if when - target > tolerance:
                continue
            actions.append(sample.action)
            futures.append(value)
        return np.asarray(actions, dtype=np.int64), np.asarray(futures, dtype=np.float64)

    def _tile_index(self) -> dict[tuple[int, int], list[tuple[int, float]]]:
        """Per-tile observation history, sorted by time, built once."""
        if self._index is None:
            index: dict[tuple[int, int], list[tuple[int, float]]] = defaultdict(list)
            for (when, x, y), value in self.tile_future.items():
                index[(x, y)].append((when, value))
            for history in index.values():
                history.sort()
            self._index = dict(index)
        return self._index

    def _sampling_interval(self) -> int:
        """Smallest gap between recorded steps: the trace's real time resolution."""
        if self._interval is None:
            steps = sorted({when for when, _, _ in self.tile_future})
            gaps = [b - a for a, b in zip(steps, steps[1:], strict=False) if b > a]
            self._interval = min(gaps) if gaps else 1
        return self._interval

    def summary(self) -> dict[str, Any]:
        return {
            "samples": len(self.samples),
            "truncated": self.truncated,
            "signal_observations": len(self.signal_observations),
            "distinct_lineages": len({s.lineage_id for s in self.samples}),
        }
