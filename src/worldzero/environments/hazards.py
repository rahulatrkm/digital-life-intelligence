"""Hazard dynamics (whitepaper section 5.5).

Hazards damage integrity rather than energy so that harm is not simply negative
food: a cell can be rich and dying, which is what makes avoidance a distinct
behaviour from foraging.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from worldzero.core.config import HazardConfig

if TYPE_CHECKING:  # pragma: no cover
    from worldzero.core.world import World


class HazardRegime:
    name = "base"

    def __init__(self, config: HazardConfig) -> None:
        self.config = config

    def initialize(self, world: World, rng) -> None:
        raise NotImplementedError

    def update(self, world: World, rng) -> None:
        return None

    def state(self) -> dict[str, Any]:
        return {}

    def restore(self, data: dict[str, Any]) -> None:
        return None

    def _scatter(self, world: World, rng) -> None:
        cfg = self.config
        count = int(cfg.initial_density * world.width * world.height)
        for _ in range(count):
            x = rng.randrange(world.width)
            y = rng.randrange(world.height)
            if not world.obstacle[y, x]:
                world.hazard[y, x] = cfg.damage_rate


class StaticToxins(HazardRegime):
    """Hazards stay put. Selects for avoidance and nothing more."""

    name = "static"

    def initialize(self, world: World, rng) -> None:
        self._scatter(world, rng)


class SpreadingToxins(HazardRegime):
    """Hazards diffuse, so a safe tile now may not be safe soon."""

    name = "spreading"

    def initialize(self, world: World, rng) -> None:
        self._scatter(world, rng)

    def update(self, world: World, rng) -> None:
        cfg = self.config
        field = world.hazard
        neighbours = (
            np.roll(field, 1, axis=0)
            + np.roll(field, -1, axis=0)
            + np.roll(field, 1, axis=1)
            + np.roll(field, -1, axis=1)
        )
        laplacian = neighbours - 4.0 * field
        field += cfg.diffusion_rate * laplacian
        field *= 1.0 - cfg.decay_rate
        np.clip(field, 0.0, None, out=field)
        field[world.obstacle] = 0.0


class DelayedToxins(HazardRegime):
    """A cue marks a tile before it becomes lethal.

    Reactive avoidance is too late by construction: by the time hazard is
    readable the damage has started, so surviving lineages must act on the cue.
    """

    name = "delayed"

    def __init__(self, config: HazardConfig) -> None:
        super().__init__(config)
        self.pending: list[tuple[int, int, int]] = []

    def initialize(self, world: World, rng) -> None:
        self._scatter(world, rng)
        self.pending = []

    def update(self, world: World, rng) -> None:
        cfg = self.config
        now = world.timestep

        ready = [p for p in self.pending if p[0] <= now]
        if ready:
            self.pending = [p for p in self.pending if p[0] > now]
            for _, x, y in ready:
                world.hazard[y, x] = cfg.damage_rate
                world.cue[y, x] = 0.0

        spawns = max(1, int(cfg.initial_density * world.width * world.height * 0.01))
        for _ in range(spawns):
            x = rng.randrange(world.width)
            y = rng.randrange(world.height)
            if world.obstacle[y, x] or world.hazard[y, x] > 0.0:
                continue
            # Negative cue so a toxin warning is distinguishable from a food
            # promise without giving the cell a labelled "danger" sensor.
            world.cue[y, x] = -1.0
            self.pending.append((now + cfg.cue_lead_time, x, y))

        world.hazard *= 1.0 - cfg.decay_rate

    def state(self) -> dict[str, Any]:
        return {"pending": [list(p) for p in self.pending]}

    def restore(self, data: dict[str, Any]) -> None:
        self.pending = [(int(a), int(b), int(c)) for a, b, c in data.get("pending", [])]


class PredatorZones(HazardRegime):
    """Moving hazards that climb the local energy gradient.

    Not agents: they carry no genome and cannot evolve. They exist to make the
    safest place depend on where the *other cells* are.
    """

    name = "predator"

    def __init__(self, config: HazardConfig) -> None:
        super().__init__(config)
        self.positions: list[tuple[int, int]] = []

    def initialize(self, world: World, rng) -> None:
        self.positions = [
            (rng.randrange(world.width), rng.randrange(world.height))
            for _ in range(self.config.predator_count)
        ]
        self._paint(world)

    def update(self, world: World, rng) -> None:
        world.hazard *= 1.0 - self.config.decay_rate
        density = world.population_density()
        moved: list[tuple[int, int]] = []
        for x, y in self.positions:
            best = (x, y)
            best_score = -1.0
            for dx, dy in ((0, 0), (0, -1), (0, 1), (-1, 0), (1, 0)):
                nx, ny = world.wrap(x + dx, y + dy)
                if nx < 0 or world.obstacle[ny, nx]:
                    continue
                score = float(density[ny, nx])
                if score > best_score:
                    best_score = score
                    best = (nx, ny)
            if best_score <= 0.0:
                dx, dy = rng.choice(((0, -1), (0, 1), (-1, 0), (1, 0)))
                nx, ny = world.wrap(x + dx, y + dy)
                if nx >= 0 and not world.obstacle[ny, nx]:
                    best = (nx, ny)
            moved.append(best)
        self.positions = moved
        self._paint(world)

    def _paint(self, world: World) -> None:
        cfg = self.config
        radius = cfg.predator_radius
        for x, y in self.positions:
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    if dx * dx + dy * dy > radius * radius:
                        continue
                    nx, ny = world.wrap(x + dx, y + dy)
                    if nx >= 0 and not world.obstacle[ny, nx]:
                        world.hazard[ny, nx] = max(world.hazard[ny, nx], cfg.damage_rate)

    def state(self) -> dict[str, Any]:
        return {"positions": [list(p) for p in self.positions]}

    def restore(self, data: dict[str, Any]) -> None:
        self.positions = [(int(a), int(b)) for a, b in data.get("positions", [])]


class SeasonalCatastrophe(HazardRegime):
    """Periodic world-wide destruction, to select over horizons longer than a life."""

    name = "seasonal"

    def initialize(self, world: World, rng) -> None:
        self._scatter(world, rng)

    def update(self, world: World, rng) -> None:
        cfg = self.config
        world.hazard *= 1.0 - cfg.decay_rate
        # timestep 0 satisfies `0 % period == 0`, so without the first guard the
        # catastrophe fires during initialisation and destroys half the founding
        # population before it has lived a step. A season arrives after a season.
        if cfg.season_period <= 0 or world.timestep == 0:
            return
        if world.timestep % cfg.season_period:
            return
        # Destroy a contiguous slab rather than random tiles: scattered damage
        # is survivable by luck, a swept region is survivable only by moving.
        band = max(1, int(world.height * cfg.season_severity))
        phase = (world.timestep // cfg.season_period) % max(1, world.height - band + 1)
        world.hazard[phase : phase + band, :] = cfg.damage_rate * 2.0
        world.resource[phase : phase + band, :] *= 0.25
        world.record_catastrophe(phase, band)


class NoHazards(HazardRegime):
    name = "none"

    def initialize(self, world: World, rng) -> None:
        return None


HAZARD_REGIMES: dict[str, type[HazardRegime]] = {
    NoHazards.name: NoHazards,
    StaticToxins.name: StaticToxins,
    SpreadingToxins.name: SpreadingToxins,
    DelayedToxins.name: DelayedToxins,
    PredatorZones.name: PredatorZones,
    SeasonalCatastrophe.name: SeasonalCatastrophe,
}


def build_hazard_regime(config: HazardConfig) -> HazardRegime:
    try:
        return HAZARD_REGIMES[config.regime](config)
    except KeyError:
        raise ValueError(
            f"Unknown hazard regime '{config.regime}'. Available: {sorted(HAZARD_REGIMES)}"
        ) from None


def seasonal_phase(timestep: int, period: int) -> float:
    """Position within the current season, in [0, 1)."""
    if period <= 0:
        return 0.0
    return (timestep % period) / period


__all__ = [
    "DelayedToxins",
    "HAZARD_REGIMES",
    "HazardRegime",
    "NoHazards",
    "PredatorZones",
    "SeasonalCatastrophe",
    "SpreadingToxins",
    "StaticToxins",
    "build_hazard_regime",
    "seasonal_phase",
]
