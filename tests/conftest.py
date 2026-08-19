"""Shared fixtures.

Tests run on a deliberately tiny world: the properties under test (energy
accounting, inheritance, decay, orphan-free lineage) are size-independent, and a
16x16 grid keeps the whole suite in the low seconds.
"""

from __future__ import annotations

import pytest

from worldzero.core.config import SimulationConfig
from worldzero.core.types import Cell, new_cell_id
from worldzero.core.world import World
from worldzero.genome.gene import random_genome

SMALL_WORLD = {
    "world": {"width": 16, "height": 16, "seed": 7},
    "cell": {"start_population": 20, "genome_length": 8},
    "stop": {"max_steps": 200},
    "logging": {"metrics_interval": 50, "trace_interval": 10, "checkpoint_interval": 0},
}


@pytest.fixture
def config() -> SimulationConfig:
    return SimulationConfig(name="test").merged(SMALL_WORLD)


@pytest.fixture
def world(config: SimulationConfig) -> World:
    return World(config)


@pytest.fixture
def empty_world(config: SimulationConfig) -> World:
    """A world with physics and terrain but no population, so a test can place
    exactly the cell it wants to reason about."""
    return World(config, populate=False)


@pytest.fixture
def place_cell():
    """Factory fixture: ``place_cell(world, x=..., y=..., energy=...)``."""
    return _place_cell


def _place_cell(world: World, x: int = 4, y: int = 4, energy: float = 50.0) -> Cell:
    """Insert one cell at a known position and register it as a founder."""
    stream = world.rng.local("test-cell", x, y)
    genome = random_genome(
        stream,
        length=4,
        max_stage=world.config.cell.max_sensor_stage,
        registers=world.config.cell.internal_registers,
        channels=world.config.physics.signal_channels,
    )
    cell_id = new_cell_id(world.rng.stream("ids"))
    cell = Cell(
        id=cell_id,
        lineage_id=cell_id,
        parent_id=None,
        generation=0,
        x=x,
        y=y,
        energy=energy,
        age=0,
        integrity=world.config.physics.integrity_max,
        genome=genome,
        internal_state=[0.0] * world.config.cell.internal_registers,
        birth_step=world.timestep,
    )
    world.cells[cell_id] = cell
    world.occupancy[(x, y)] = cell_id
    world.lineage.register_founder(cell)
    world.ledger.initial_endowment += energy
    return cell
