"""Environment engine (whitepaper sections 5.4, 5.5 and 11).

Combines one resource regime and one hazard regime behind a single object so
the simulation core never needs to know which regime is running -- swapping
environments is a config change, which is what the staged experiments require.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import numpy as np

from worldzero.environments.hazards import (
    HAZARD_REGIMES,
    HazardRegime,
    build_hazard_regime,
)
from worldzero.environments.resources import (
    RESOURCE_REGIMES,
    ResourceRegime,
    build_resource_regime,
)

if TYPE_CHECKING:  # pragma: no cover
    from worldzero.core.config import SimulationConfig
    from worldzero.core.world import World

__all__ = [
    "HAZARD_REGIMES",
    "RESOURCE_REGIMES",
    "Environment",
    "HazardRegime",
    "ResourceRegime",
    "build_hazard_regime",
    "build_resource_regime",
]


class Environment:
    def __init__(self, config: SimulationConfig) -> None:
        self.config = config
        self.resources: ResourceRegime = build_resource_regime(config.resources)
        self.hazards: HazardRegime = build_hazard_regime(config.hazards)

    def initialize(self, world: World) -> None:
        rng = world.rng.stream("environment-init")
        if world.config.world.obstacle_density > 0:
            density = world.config.world.obstacle_density
            noise = np.asarray(
                [
                    [rng.random() for _ in range(world.width)]
                    for _ in range(world.height)
                ],
                dtype=np.float32,
            )
            world.obstacle = noise < density
        self.resources.initialize(world, rng)
        self.hazards.initialize(world, rng)

    def update(self, world: World) -> None:
        """Whitepaper section 7.1, ``update_environment``."""
        if self.config.controls.static_environment:
            # Section 17 control: freeze the world to test whether environmental
            # change is required for the higher emergence stages at all.
            return
        rng = world.rng.stream("environment")
        self.resources.update(world, rng)
        self.hazards.update(world, rng)
        if self.config.physics.marker_decay < 1.0:
            world.marker *= self.config.physics.marker_decay

    def state(self) -> dict[str, Any]:
        return {"resources": self.resources.state(), "hazards": self.hazards.state()}

    def restore(self, data: dict[str, Any]) -> None:
        self.resources.restore(data.get("resources", {}))
        self.hazards.restore(data.get("hazards", {}))
