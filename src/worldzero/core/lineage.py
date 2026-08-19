"""Lineage tracking (whitepaper section 11, 'Lineage tracker').

Section 8 draws the distinction the whole project rests on: a cell dies, a
lineage learns. Fitness therefore has to be attributable to a lineage, not just
to an individual, so ancestry is recorded as a first-class edge list rather than
reconstructed from the event log after the fact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # pragma: no cover
    from worldzero.core.types import Cell


@dataclass(slots=True)
class LineageStats:
    lineage_id: str
    founder_id: str
    births: int = 0
    deaths: int = 0
    alive: int = 0
    max_generation: int = 0
    total_lifespan: int = 0
    total_offspring: int = 0
    total_energy_consumed: float = 0.0
    first_step: int = 0
    last_step: int = 0
    genome_hashes: set[str] = field(default_factory=set)

    @property
    def mean_lifespan(self) -> float:
        return self.total_lifespan / self.deaths if self.deaths else 0.0

    @property
    def mean_offspring(self) -> float:
        return self.total_offspring / self.deaths if self.deaths else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "lineage_id": self.lineage_id,
            "founder_id": self.founder_id,
            "births": self.births,
            "deaths": self.deaths,
            "alive": self.alive,
            "max_generation": self.max_generation,
            "mean_lifespan": round(self.mean_lifespan, 4),
            "mean_offspring": round(self.mean_offspring, 4),
            "total_energy_consumed": round(self.total_energy_consumed, 4),
            "distinct_genomes": len(self.genome_hashes),
            "first_step": self.first_step,
            "last_step": self.last_step,
        }


class LineageTracker:
    """Ancestry edge list plus per-lineage aggregates.

    Full parent->child edges are optional because a million-step run produces
    tens of millions of them; aggregates are always kept.
    """

    def __init__(self, *, keep_edges: bool = True, max_edges: int = 2_000_000) -> None:
        self.keep_edges = keep_edges
        self.max_edges = max_edges
        self.edges: list[tuple[str, str]] = []
        self.edges_truncated = False
        self.lineages: dict[str, LineageStats] = {}
        self.founders: set[str] = set()
        self._known_cells: set[str] = set()
        self.lifespans: list[int] = []
        self.orphans: list[str] = []

    # -- recording ------------------------------------------------------------

    def register_founder(self, cell: Cell) -> None:
        self.founders.add(cell.id)
        self._known_cells.add(cell.id)
        stats = self._stats(cell)
        stats.births += 1
        stats.alive += 1
        stats.genome_hashes.add(cell.genome.hash)

    def register_birth(self, child: Cell, parent: Cell, timestep: int) -> None:
        if parent.id not in self._known_cells:
            # Should be impossible; recorded rather than raised so a long run is
            # not lost to a bookkeeping bug, and asserted on in the test suite.
            self.orphans.append(child.id)
        self._known_cells.add(child.id)
        if self.keep_edges:
            if len(self.edges) < self.max_edges:
                self.edges.append((parent.id, child.id))
            else:
                self.edges_truncated = True
        stats = self._stats(child)
        stats.births += 1
        stats.alive += 1
        stats.max_generation = max(stats.max_generation, child.generation)
        stats.last_step = timestep
        stats.genome_hashes.add(child.genome.hash)

    def register_death(self, cell: Cell, timestep: int) -> None:
        stats = self.lineages.get(cell.lineage_id)
        if stats is None:
            return
        stats.deaths += 1
        stats.alive = max(0, stats.alive - 1)
        lifespan = cell.lifespan(timestep)
        stats.total_lifespan += lifespan
        stats.total_offspring += cell.offspring_count
        stats.total_energy_consumed += cell.energy_consumed
        stats.last_step = timestep
        self.lifespans.append(lifespan)

    def register_existing(self, cell: Cell) -> None:
        """Re-seed the tracker from a checkpoint without inventing birth events."""
        self._known_cells.add(cell.id)
        if cell.parent_id is None:
            self.founders.add(cell.id)
        stats = self._stats(cell)
        stats.alive += 1
        stats.max_generation = max(stats.max_generation, cell.generation)
        stats.genome_hashes.add(cell.genome.hash)

    def _stats(self, cell: Cell) -> LineageStats:
        stats = self.lineages.get(cell.lineage_id)
        if stats is None:
            stats = LineageStats(
                lineage_id=cell.lineage_id,
                founder_id=cell.id if cell.parent_id is None else cell.lineage_id,
                first_step=cell.birth_step,
            )
            self.lineages[cell.lineage_id] = stats
        return stats

    # -- querying -------------------------------------------------------------

    @property
    def surviving_lineages(self) -> list[LineageStats]:
        return [s for s in self.lineages.values() if s.alive > 0]

    def mean_lifespan(self) -> float:
        return sum(self.lifespans) / len(self.lifespans) if self.lifespans else 0.0

    def median_lifespan(self) -> float:
        if not self.lifespans:
            return 0.0
        ordered = sorted(self.lifespans)
        mid = len(ordered) // 2
        if len(ordered) % 2:
            return float(ordered[mid])
        return (ordered[mid - 1] + ordered[mid]) / 2.0

    def max_generation(self) -> int:
        return max((s.max_generation for s in self.lineages.values()), default=0)

    def has_orphans(self) -> bool:
        return bool(self.orphans)

    # -- checkpointing --------------------------------------------------------

    def state(self) -> dict[str, Any]:
        """Aggregates a resumed run needs to keep reporting history correctly.

        The parent->child edge list is deliberately excluded: it is already
        optional at runtime and would dominate the checkpoint size.
        """
        return {
            "founders": sorted(self.founders),
            "lifespans": list(self.lifespans),
            "orphans": list(self.orphans),
            "edges_truncated": self.edges_truncated,
            "lineages": [
                {
                    "lineage_id": s.lineage_id,
                    "founder_id": s.founder_id,
                    "births": s.births,
                    "deaths": s.deaths,
                    "alive": s.alive,
                    "max_generation": s.max_generation,
                    "total_lifespan": s.total_lifespan,
                    "total_offspring": s.total_offspring,
                    "total_energy_consumed": s.total_energy_consumed,
                    "first_step": s.first_step,
                    "last_step": s.last_step,
                    "genome_hashes": sorted(s.genome_hashes),
                }
                for s in self.lineages.values()
            ],
        }

    def load_state(self, data: dict[str, Any]) -> None:
        """Restore aggregates saved by :meth:`state`.

        Call before re-registering live cells: ``register_existing`` increments
        ``alive``, which would double-count against the restored figure.
        """
        if not data:
            return
        self.founders = set(data.get("founders", []))
        self.lifespans = list(data.get("lifespans", []))
        self.orphans = list(data.get("orphans", []))
        self.edges_truncated = bool(data.get("edges_truncated", False))
        self.lineages = {}
        for entry in data.get("lineages", []):
            stats = LineageStats(
                lineage_id=entry["lineage_id"],
                founder_id=entry["founder_id"],
                births=entry.get("births", 0),
                deaths=entry.get("deaths", 0),
                alive=0,
                max_generation=entry.get("max_generation", 0),
                total_lifespan=entry.get("total_lifespan", 0),
                total_offspring=entry.get("total_offspring", 0),
                total_energy_consumed=entry.get("total_energy_consumed", 0.0),
                first_step=entry.get("first_step", 0),
                last_step=entry.get("last_step", 0),
                genome_hashes=set(entry.get("genome_hashes", [])),
            )
            self.lineages[stats.lineage_id] = stats

    def summary(self, top: int = 10) -> dict[str, Any]:
        ranked = sorted(
            self.lineages.values(),
            key=lambda s: (s.alive, s.births),
            reverse=True,
        )[:top]
        return {
            "total_lineages": len(self.lineages),
            "surviving_lineages": len(self.surviving_lineages),
            "founders": len(self.founders),
            "max_generation": self.max_generation(),
            "mean_lifespan": round(self.mean_lifespan(), 4),
            "median_lifespan": round(self.median_lifespan(), 4),
            "orphans": len(self.orphans),
            "edges_truncated": self.edges_truncated,
            "top_lineages": [s.to_dict() for s in ranked],
        }
