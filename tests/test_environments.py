"""Environment regime timing and supply.

Regressions for two defects that silently invalidated whole experiments: a
periodic catastrophe that fired during initialisation, and supply knobs that a
regime does not actually read.
"""

from __future__ import annotations

import numpy as np
import pytest

from worldzero.core.config import SimulationConfig
from worldzero.core.world import World

SEASONAL = {
    "world": {"width": 32, "height": 32, "seed": 3},
    "cell": {"start_population": 40},
    "hazards": {"regime": "seasonal", "season_period": 50, "season_severity": 0.5},
    "resources": {"regime": "regenerating"},
}


def _seasonal_world() -> World:
    return World(SimulationConfig(name="seasonal").merged(SEASONAL))


def test_catastrophe_does_not_fire_at_initialisation() -> None:
    """A season must arrive after a season, not at t=0."""
    world = _seasonal_world()
    baseline = float(world.hazard.sum())

    world.step()

    # Only the scattered baseline hazard should be present, not a swept slab.
    assert float(world.hazard.sum()) <= baseline
    assert float(world.hazard.max()) < world.config.hazards.damage_rate * 2.0


def test_catastrophe_fires_on_schedule() -> None:
    world = _seasonal_world()
    period = world.config.hazards.season_period

    # `timestep` increments at the end of step(), and environment.update() runs
    # at the start, so the slab lands on the step that *begins* at t == period.
    for _ in range(period):
        world.step()
    assert world.timestep == period
    quiet = float(world.hazard.max())

    world.step()

    assert float(world.hazard.max()) >= world.config.hazards.damage_rate * 2.0
    assert float(world.hazard.max()) > quiet


def test_founders_survive_the_first_step() -> None:
    """Half the founding population used to die within three steps of creation."""
    world = _seasonal_world()
    founders = world.population

    for _ in range(3):
        world.step()

    assert world.population >= founders * 0.9


@pytest.mark.parametrize(
    ("regime", "field"),
    [("regenerating", "regen_rate"), ("cyclic", "regen_rate"), ("scarce", "regen_rate")],
)
def test_regen_rate_actually_moves_supply(regime: str, field: str) -> None:
    """Guards against tuning a knob the regime never reads."""

    def delivered(rate: float) -> float:
        config = SimulationConfig(name="supply").merged(
            {
                "world": {"width": 32, "height": 32, "seed": 5},
                "cell": {"start_population": 0},
                "resources": {"regime": regime, field: rate},
                "hazards": {"regime": "none"},
            }
        )
        world = World(config, populate=False)
        world.resource[:] = 0.0
        for _ in range(400):
            world.step()
        return float(world.resource.sum())

    assert delivered(0.20) > delivered(0.02)


def test_hidden_regime_ignores_regen_rate() -> None:
    """Documents why the calibration scales density, not regen, for `hidden`."""

    def delivered(rate: float) -> float:
        config = SimulationConfig(name="hidden").merged(
            {
                "world": {"width": 32, "height": 32, "seed": 5},
                "cell": {"start_population": 0},
                "resources": {"regime": "hidden", "regen_rate": rate},
                "hazards": {"regime": "none"},
            }
        )
        world = World(config, populate=False)
        for _ in range(300):
            world.step()
        return float(world.resource.sum())

    assert delivered(0.20) == delivered(0.02)


def test_cyclic_delivers_less_than_regenerating_at_equal_rate() -> None:
    """Rectifying a sine yields ~1/pi of the nominal rate, so the two regimes are
    not comparable at the same regen_rate."""
    period = 200

    def delivered(regime: str) -> float:
        config = SimulationConfig(name=regime).merged(
            {
                "world": {"width": 32, "height": 32, "seed": 5},
                "cell": {"start_population": 0},
                # Low rate over exactly one cycle: high rates saturate at
                # max_per_tile, which hides the difference being measured.
                "resources": {"regime": regime, "regen_rate": 0.01, "cycle_period": period},
                "hazards": {"regime": "none"},
            }
        )
        world = World(config, populate=False)
        world.resource[:] = 0.0
        for _ in range(period):
            world.step()
        assert float(world.resource.max()) < config.resources.max_per_tile
        return float(world.resource.sum())

    cyclic = delivered("cyclic")
    regenerating = delivered("regenerating")
    assert cyclic < regenerating
    assert cyclic == pytest.approx(regenerating / np.pi, rel=0.25)
