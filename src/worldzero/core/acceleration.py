"""Time acceleration (whitepaper section 10).

Section 10.2 asks for event-based stepping: fast-forward stable windows,
simulate everything else exactly. The awkward part is that "stable population"
is not the same as "nothing is happening" -- a population can hold a flat count
while cells forage, breed and die underneath. Bulk-advancing that period would
starve everyone, because the closed-form model has no consumption in it.

Skipping therefore requires the world to be *quiescent*: flat population, no
births, no deaths and no harvesting across the whole window. In that regime the
only things changing are environment fields (already vectorised), cell age and
cell energy burn, all of which advance analytically.

Section 10.3 still applies: every skipped window is recorded so metrics can be
stratified, and :func:`validate_against_exact` re-runs a window step by step to
measure the divergence rather than assuming there is none.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from worldzero.core.config import AccelerationConfig
from worldzero.core.types import ActionType
from worldzero.storage.events import EventType

if TYPE_CHECKING:  # pragma: no cover
    from worldzero.core.world import World


@dataclass
class AccelerationRecord:
    start: int
    end: int
    skipped: int


@dataclass(slots=True)
class _Observation:
    population: int
    births: int
    deaths: int
    harvested: float


@dataclass
class Accelerator:
    config: AccelerationConfig
    history: list[_Observation] = field(default_factory=list)
    records: list[AccelerationRecord] = field(default_factory=list)
    total_skipped: int = 0

    def observe(self, world: World) -> None:
        self.history.append(
            _Observation(
                population=world.population,
                births=world.births,
                deaths=world.deaths,
                harvested=world.ledger.harvested,
            )
        )
        window = self.config.stability_window
        if len(self.history) > window * 2:
            del self.history[:window]

    def is_quiescent(self) -> bool:
        """Whitepaper section 10.2, ``world_is_stable_for_window``, strengthened."""
        window = self.config.stability_window
        if len(self.history) < window:
            return False
        recent = self.history[-window:]
        first, last = recent[0], recent[-1]

        if last.births != first.births or last.deaths != first.deaths:
            return False
        if last.harvested - first.harvested > 1e-9:
            return False

        counts = [o.population for o in recent]
        mean = sum(counts) / len(counts)
        if mean <= 0:
            return False
        return (max(counts) - min(counts)) / mean <= self.config.stability_tolerance

    def next_event_horizon(self, world: World) -> int:
        """Steps until something is guaranteed to happen."""
        physics = world.config.physics
        limits = [self.config.max_skip]

        period = world.config.hazards.season_period
        if world.config.hazards.regime == "seasonal" and period > 0:
            limits.append(period - (world.timestep % period))

        cells = world.living_cells()
        if not cells:
            return 0

        limits.append(max(1, physics.max_age - max(c.age for c in cells)))

        for cell in cells:
            burn = self._burn_rate(cell, world)
            if burn > 1e-9:
                limits.append(max(1, int(cell.energy / burn)))

        return max(0, min(limits))

    def maybe_skip(self, world: World) -> int:
        """Fast-forward a quiescent window. Returns the number of steps skipped."""
        if not self.config.enabled or not self.is_quiescent():
            return 0
        if self.config.exact_validation_interval and (
            world.timestep % self.config.exact_validation_interval
            < self.config.stability_window
        ):
            # Refuse to accelerate periodically so exact and accelerated windows
            # exist on the same run and can be compared (section 17).
            return 0

        horizon = self.next_event_horizon(world)
        if horizon < 2:
            return 0

        start = world.timestep
        self._bulk_advance(world, horizon)
        skipped = world.timestep - start

        self.records.append(AccelerationRecord(start=start, end=world.timestep, skipped=skipped))
        self.total_skipped += skipped
        if world.event_log is not None:
            world.event_log.emit(
                EventType.ACCELERATION,
                world.timestep,
                payload={"from": start, "to": world.timestep, "steps": skipped},
            )
        self.history.clear()
        return skipped

    # -- the approximation ----------------------------------------------------

    @staticmethod
    def _burn_rate(cell, world: World) -> float:
        """Energy per step if the cell keeps repeating its last action."""
        physics = world.config.physics
        sensing = physics.sense_cost * len(cell.genome.enabled_sensors())
        kind = cell.last_action.type if cell.last_action else ActionType.STAY
        if kind is ActionType.MOVE:
            return sensing + physics.move_cost
        if kind is ActionType.EMIT:
            return sensing + physics.signal_cost
        if kind is ActionType.PROBE:
            return sensing + physics.probe_cost
        return sensing + physics.idle_cost

    def _bulk_advance(self, world: World, steps: int) -> None:
        ledger = world.ledger
        for _ in range(steps):
            world.environment.update(world)
            world.timestep += 1

        for cell in list(world.cells.values()):
            burn = self._burn_rate(cell, world) * steps
            cell.energy -= burn
            ledger.spent_idle += burn
            cell.age += steps
            damage = float(world.hazard[cell.y, cell.x])
            if damage > 0.0:
                cell.integrity -= damage * 0.1 * steps

            reason = world.should_die(cell)
            if reason is not None:
                world.kill(cell, reason)
                world.cells.pop(cell.id, None)

        world.decay_signals()

    def summary(self) -> dict[str, float | int]:
        return {
            "windows": len(self.records),
            "total_skipped": self.total_skipped,
            "enabled": self.config.enabled,
        }


def validate_against_exact(config, steps: int, *, seed: int | None = None) -> dict[str, float]:
    """Run the same world with and without acceleration and report divergence.

    Whitepaper section 19 lists "acceleration artifact" as a named failure whose
    diagnostic is "fast run differs from exact run", so this returns the actual
    numbers rather than a pass/fail.
    """
    from worldzero.core.world import World

    if seed is not None:
        config = config.with_seed(seed)

    exact_config = config.merged({"acceleration": {"enabled": False}})
    fast_config = config.merged({"acceleration": {"enabled": True}})

    exact = World(exact_config)
    for _ in range(steps):
        exact.step()

    fast = World(fast_config)
    accelerator = Accelerator(fast_config.acceleration)
    while fast.timestep < steps:
        accelerator.observe(fast)
        if accelerator.maybe_skip(fast):
            continue
        fast.step()

    exact_stats = exact.stats()
    fast_stats = fast.stats()
    denominator = max(1.0, float(exact_stats["population"]))
    return {
        "exact_population": float(exact_stats["population"]),
        "accelerated_population": float(fast_stats["population"]),
        "population_divergence": abs(
            float(exact_stats["population"]) - float(fast_stats["population"])
        )
        / denominator,
        "exact_births": float(exact_stats["births"]),
        "accelerated_births": float(fast_stats["births"]),
        "steps_skipped": float(accelerator.total_skipped),
        "windows": float(len(accelerator.records)),
    }
