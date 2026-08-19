"""Resource dynamics (whitepaper section 5.4).

The regimes are ordered by the capability they put pressure on: static patches
select for movement, regenerating patches for memory, cycles for prediction,
moving fronts for tracking, hidden resources for anticipation, scarcity for
competition. Nothing here rewards a cell directly -- resources only change what
is available to convert into energy.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

import numpy as np

from worldzero.core.config import ResourceConfig

if TYPE_CHECKING:  # pragma: no cover
    from worldzero.core.world import World


class ResourceRegime:
    name = "base"

    def __init__(self, config: ResourceConfig) -> None:
        self.config = config

    def initialize(self, world: World, rng) -> None:
        raise NotImplementedError

    def update(self, world: World, rng) -> None:
        return None

    def state(self) -> dict[str, Any]:
        return {}

    def restore(self, data: dict[str, Any]) -> None:
        return None

    # -- shared helpers -------------------------------------------------------

    def _seed_patches(self, world: World, rng) -> np.ndarray:
        """Scatter circular patches and return the mask of tiles that may hold food."""
        cfg = self.config
        h, w = world.height, world.width
        mask = np.zeros((h, w), dtype=bool)
        area = h * w
        radius = max(1, cfg.patch_radius)
        per_patch = math.pi * radius * radius
        target = cfg.initial_density * cfg.scarcity_factor * area
        patch_count = max(1, int(round(target / per_patch)))

        ys, xs = np.ogrid[:h, :w]
        for _ in range(patch_count):
            cx = rng.randrange(w)
            cy = rng.randrange(h)
            dx = np.minimum(np.abs(xs - cx), w - np.abs(xs - cx)) if world.wrap_enabled else xs - cx
            dy = np.minimum(np.abs(ys - cy), h - np.abs(ys - cy)) if world.wrap_enabled else ys - cy
            mask |= (dx * dx + dy * dy) <= radius * radius

        mask &= ~world.obstacle
        world.resource[mask] = cfg.max_per_tile
        return mask

    def _apply_variants(self, world: World, mask: np.ndarray, rng) -> None:
        """Give functionally identical resources different surface signatures.

        Used by the abstraction experiment (section 16.7): energy yield is the
        same for every variant, only the observable cue differs, so responding
        to the whole signature range is genuinely more general than responding
        to the particular values a lineage happened to meet.
        """
        variants = max(1, self.config.variants)
        if variants == 1:
            world.variant[:] = 0
            return
        indices = np.argwhere(mask)
        for y, x in indices:
            variant = rng.randrange(variants)
            world.variant[y, x] = variant
            world.cue[y, x] = world.variant_signature(variant)


class StaticPatches(ResourceRegime):
    """Resources appear in fixed locations and are never replenished."""

    name = "static"

    def initialize(self, world: World, rng) -> None:
        mask = self._seed_patches(world, rng)
        self._apply_variants(world, mask, rng)


class RegeneratingPatches(ResourceRegime):
    """Resources reappear after depletion, so where food *was* stays informative."""

    name = "regenerating"

    def __init__(self, config: ResourceConfig) -> None:
        super().__init__(config)
        self.mask: np.ndarray | None = None

    def initialize(self, world: World, rng) -> None:
        self.mask = self._seed_patches(world, rng)
        self._apply_variants(world, self.mask, rng)

    def update(self, world: World, rng) -> None:
        if self.mask is None:
            return
        cfg = self.config
        np.add(world.resource, cfg.regen_rate * self.mask, out=world.resource)
        np.clip(world.resource, 0.0, cfg.max_per_tile, out=world.resource)

    def state(self) -> dict[str, Any]:
        return {"mask": None if self.mask is None else self.mask.astype(np.uint8).tolist()}

    def restore(self, data: dict[str, Any]) -> None:
        mask = data.get("mask")
        if mask is not None:
            self.mask = np.asarray(mask, dtype=np.uint8).astype(bool)


class CyclicResources(RegeneratingPatches):
    """Regeneration follows a fixed temporal cycle: the same place is rich, then poor."""

    name = "cyclic"

    def update(self, world: World, rng) -> None:
        if self.mask is None:
            return
        cfg = self.config
        phase = 2.0 * math.pi * (world.timestep % cfg.cycle_period) / cfg.cycle_period
        rate = cfg.regen_rate * max(0.0, math.sin(phase))
        np.add(world.resource, rate * self.mask, out=world.resource)
        np.clip(world.resource, 0.0, cfg.max_per_tile, out=world.resource)


class MovingFront(ResourceRegime):
    """A band of fertility sweeps across the world; standing still starves."""

    name = "moving_front"

    def __init__(self, config: ResourceConfig) -> None:
        super().__init__(config)
        self.position = 0.0
        self.width_fraction = 0.15

    def initialize(self, world: World, rng) -> None:
        self.position = float(rng.randrange(world.width))
        self._deposit(world)

    def update(self, world: World, rng) -> None:
        self.position = (self.position + self.config.front_speed) % world.width
        self._deposit(world)

    def _deposit(self, world: World) -> None:
        cfg = self.config
        band = max(1, int(world.width * self.width_fraction))
        columns = [(int(self.position) + i) % world.width for i in range(band)]
        world.resource[:, columns] = np.minimum(
            world.resource[:, columns] + cfg.regen_rate * 4.0, cfg.max_per_tile
        )
        world.resource[world.obstacle] = 0.0

    def state(self) -> dict[str, Any]:
        return {"position": self.position}

    def restore(self, data: dict[str, Any]) -> None:
        self.position = float(data.get("position", 0.0))


class HiddenResources(ResourceRegime):
    """A cue appears ``cue_lead_time`` steps before the food does.

    This is the environment that separates reaction from anticipation: at the
    moment the cue is visible there is nothing to consume, so any behaviour that
    pays off must be driven by the cue rather than by the resource.
    """

    name = "hidden"

    def __init__(self, config: ResourceConfig) -> None:
        super().__init__(config)
        self.mask: np.ndarray | None = None
        self.pending: list[tuple[int, int, int, float]] = []

    def initialize(self, world: World, rng) -> None:
        self.mask = self._seed_patches(world, rng)
        self._apply_variants(world, self.mask, rng)
        self.pending = []

    def update(self, world: World, rng) -> None:
        if self.mask is None:
            return
        cfg = self.config
        now = world.timestep

        ready = [p for p in self.pending if p[0] <= now]
        if ready:
            self.pending = [p for p in self.pending if p[0] > now]
            for _, x, y, amount in ready:
                world.resource[y, x] = min(cfg.max_per_tile, world.resource[y, x] + amount)
                world.hidden_resource[y, x] = 0.0
                world.cue[y, x] = 0.0

        candidates = int(self.mask.sum() * 0.002) + 1
        for _ in range(candidates):
            y = rng.randrange(world.height)
            x = rng.randrange(world.width)
            if not self.mask[y, x] or world.resource[y, x] > 0.1:
                continue
            amount = cfg.max_per_tile
            world.cue[y, x] = cfg.cue_strength
            world.hidden_resource[y, x] = amount
            self.pending.append((now + cfg.cue_lead_time, x, y, amount))

    def state(self) -> dict[str, Any]:
        return {
            "mask": None if self.mask is None else self.mask.astype(np.uint8).tolist(),
            "pending": [list(p) for p in self.pending],
        }

    def restore(self, data: dict[str, Any]) -> None:
        mask = data.get("mask")
        if mask is not None:
            self.mask = np.asarray(mask, dtype=np.uint8).astype(bool)
        self.pending = [
            (int(a), int(b), int(c), float(d)) for a, b, c, d in data.get("pending", [])
        ]


class ScarceResources(RegeneratingPatches):
    """Regenerating patches at a fraction of the usual supply, to force competition."""

    name = "scarce"

    def update(self, world: World, rng) -> None:
        if self.mask is None:
            return
        cfg = self.config
        rate = cfg.regen_rate * cfg.scarcity_factor
        np.add(world.resource, rate * self.mask, out=world.resource)
        np.clip(world.resource, 0.0, cfg.max_per_tile, out=world.resource)


RESOURCE_REGIMES: dict[str, type[ResourceRegime]] = {
    StaticPatches.name: StaticPatches,
    RegeneratingPatches.name: RegeneratingPatches,
    CyclicResources.name: CyclicResources,
    MovingFront.name: MovingFront,
    HiddenResources.name: HiddenResources,
    ScarceResources.name: ScarceResources,
}


def build_resource_regime(config: ResourceConfig) -> ResourceRegime:
    try:
        return RESOURCE_REGIMES[config.regime](config)
    except KeyError:
        raise ValueError(
            f"Unknown resource regime '{config.regime}'. "
            f"Available: {sorted(RESOURCE_REGIMES)}"
        ) from None
