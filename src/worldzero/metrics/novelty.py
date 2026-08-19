"""Behavioural novelty with a persistence filter (whitepaper sections 15.1, 15.2).

Section 15.2 is the important constraint: a one-step mutant is not novelty. An
archive of raw behaviour signatures will happily report unbounded novelty in a
population that is doing nothing but drifting, because every mutation perturbs
the signature slightly. A candidate therefore only enters the archive once it
has been observed in enough distinct generations to show it is heritable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import numpy as np

from worldzero.core.types import ActionType

if TYPE_CHECKING:  # pragma: no cover
    from worldzero.core.types import Cell

_ACTION_COUNT = len(ActionType)


def behaviour_signature(cells: list[Cell]) -> np.ndarray:
    """Describe what a group of cells is built to do.

    Derived from genome structure rather than realised actions so the signature
    is a property of the lineage, not of the tile it happened to be standing on.
    """
    if not cells:
        return np.zeros(_ACTION_COUNT + 4, dtype=np.float64)

    actions = np.zeros(_ACTION_COUNT, dtype=np.float64)
    sensors: set[int] = set()
    lengths: list[float] = []
    memory_genes = 0.0
    signal_genes = 0.0

    for cell in cells:
        for gene in cell.genome.genes:
            actions[int(gene.action)] += 1.0
            sensors.add(int(gene.sensor_id))
            if gene.memory_read_index is not None or gene.memory_write_index is not None:
                memory_genes += 1.0
            if gene.action is ActionType.EMIT:
                signal_genes += 1.0
        lengths.append(float(len(cell.genome)))

    total = actions.sum() or 1.0
    return np.concatenate(
        [
            actions / total,
            [
                len(sensors) / 24.0,
                float(np.mean(lengths)) / 64.0,
                memory_genes / total,
                signal_genes / total,
            ],
        ]
    )


@dataclass
class NoveltyArchive:
    """Persistence-filtered archive of behaviour signatures."""

    threshold: float = 0.15
    min_generations: int = 3
    archive: list[np.ndarray] = field(default_factory=list)
    pending: list[tuple[np.ndarray, set[int]]] = field(default_factory=list)
    accepted: int = 0
    rejected_transient: int = 0
    history: list[float] = field(default_factory=list)

    def distance(self, signature: np.ndarray) -> float:
        """Euclidean distance to the nearest archived signature."""
        if not self.archive:
            return float("inf")
        stacked = np.vstack(self.archive)
        return float(np.linalg.norm(stacked - signature, axis=1).min())

    def observe(self, signature: np.ndarray, generation: int) -> float:
        distance = self.distance(signature)
        self.history.append(0.0 if distance == float("inf") else distance)

        if distance < self.threshold:
            return distance

        # Candidates are matched by proximity, not by an exact key. The
        # signature is a continuous population average, so hashing it means two
        # near-identical behaviours are different candidates and none ever
        # recurs -- the archive then stays empty however much evolution happens.
        index = self._nearest_pending(signature)
        if index is None:
            self.pending.append((signature, {generation}))
            return distance

        stored, generations = self.pending[index]
        generations.add(generation)
        if len(generations) >= self.min_generations:
            self.archive.append(stored)
            self.accepted += 1
            self.pending.pop(index)
        return distance

    def _nearest_pending(self, signature: np.ndarray) -> int | None:
        if not self.pending:
            return None
        stacked = np.vstack([candidate for candidate, _ in self.pending])
        distances = np.linalg.norm(stacked - signature, axis=1)
        best = int(np.argmin(distances))
        return best if float(distances[best]) < self.threshold else None

    def prune(self, current_generation: int, window: int = 20) -> None:
        """Drop candidates that stopped recurring: they were transient mutants."""
        kept: list[tuple[np.ndarray, set[int]]] = []
        for candidate, generations in self.pending:
            if generations and current_generation - max(generations) > window:
                self.rejected_transient += 1
            else:
                kept.append((candidate, generations))
        self.pending = kept

    def summary(self) -> dict[str, float | int]:
        recent = self.history[-50:]
        return {
            "archive_size": len(self.archive),
            "accepted": self.accepted,
            "rejected_transient": self.rejected_transient,
            "pending": len(self.pending),
            "mean_recent_distance": round(float(np.mean(recent)), 6) if recent else 0.0,
        }


def policy_entropy(cells: list[Cell]) -> float:
    """Entropy over the action distribution the population's genomes encode."""
    if not cells:
        return 0.0
    counts = np.zeros(_ACTION_COUNT, dtype=np.float64)
    for cell in cells:
        for gene in cell.genome.genes:
            counts[int(gene.action)] += 1.0
    total = counts.sum()
    if total <= 0:
        return 0.0
    probabilities = counts[counts > 0] / total
    return float(-np.sum(probabilities * np.log2(probabilities)))
