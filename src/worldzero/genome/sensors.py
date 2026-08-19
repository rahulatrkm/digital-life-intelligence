"""Sensor reads (whitepaper section 6.2).

Sensors may access only local or explicitly allowed environmental state
(invariant 4.3). Every read here touches the cell's own tile or its immediate
neighbourhood; nothing reads global state, future state, or evaluator data.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from worldzero.genome.gene import MEMORY_SENSORS, SIGNAL_SENSORS, Sensor

if TYPE_CHECKING:  # pragma: no cover
    from worldzero.core.types import Cell
    from worldzero.core.world import World

_NEIGHBOURS_8 = ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))

_RESOURCE_GRADIENTS = {
    Sensor.RESOURCE_GRADIENT_NORTH: (0, -1),
    Sensor.RESOURCE_GRADIENT_SOUTH: (0, 1),
    Sensor.RESOURCE_GRADIENT_EAST: (1, 0),
    Sensor.RESOURCE_GRADIENT_WEST: (-1, 0),
}

_HAZARD_GRADIENTS = {
    Sensor.HAZARD_GRADIENT_NORTH: (0, -1),
    Sensor.HAZARD_GRADIENT_SOUTH: (0, 1),
    Sensor.HAZARD_GRADIENT_EAST: (1, 0),
    Sensor.HAZARD_GRADIENT_WEST: (-1, 0),
}


def read_sensor(sensor: Sensor, cell: Cell, world: World) -> float:
    """Return the value of one sensor for one cell. Charging is the caller's job."""
    x, y = cell.x, cell.y

    if sensor is Sensor.RESOURCE_HERE:
        return float(world.resource[y, x])

    if sensor in _RESOURCE_GRADIENTS:
        dx, dy = _RESOURCE_GRADIENTS[sensor]
        nx, ny = world.wrap(x + dx, y + dy)
        if nx < 0:
            return 0.0
        return float(world.resource[ny, nx] - world.resource[y, x])

    if sensor is Sensor.HAZARD_HERE:
        return float(world.hazard[y, x])

    if sensor in _HAZARD_GRADIENTS:
        dx, dy = _HAZARD_GRADIENTS[sensor]
        nx, ny = world.wrap(x + dx, y + dy)
        if nx < 0:
            return 0.0
        return float(world.hazard[ny, nx] - world.hazard[y, x])

    if sensor is Sensor.ENERGY_LEVEL:
        return float(cell.energy)

    if sensor is Sensor.AGE:
        return float(cell.age)

    if sensor is Sensor.CUE_HERE:
        return float(world.cue[y, x])

    if sensor is Sensor.MARKER_HERE:
        controls = world.config.controls
        if controls.disable_markers or controls.isolate_cells:
            return 0.0
        return float(world.marker[y, x])

    if sensor is Sensor.CELL_DENSITY:
        if world.config.controls.isolate_cells:
            return 0.0
        count = 0
        for dx, dy in _NEIGHBOURS_8:
            nx, ny = world.wrap(x + dx, y + dy)
            if nx >= 0 and (nx, ny) in world.occupancy:
                count += 1
        return float(count)

    if sensor in MEMORY_SENSORS:
        index = MEMORY_SENSORS.index(sensor)
        controls = world.config.controls
        if controls.disable_memory or index >= len(cell.internal_state):
            return 0.0
        if controls.scramble_memory:
            # Preserve the marginal distribution of register values but destroy
            # the correspondence with what the cell actually stored -- section
            # 17 wants to test whether the *content* matters, not its presence.
            return world.scrambled_memory_value(cell, index)
        return float(cell.internal_state[index])

    if sensor in SIGNAL_SENSORS:
        channel = SIGNAL_SENSORS.index(sensor)
        if channel >= world.signal_field.shape[0]:
            return 0.0
        if world.config.controls.isolate_cells:
            # Isolation has to cut every channel between cells, not just the
            # density sensor, or "isolated" cells still coordinate via signals.
            return 0.0
        if world.config.controls.scramble_signals:
            return world.scrambled_signal_value(channel)
        return float(world.signal_field[channel, y, x])

    return 0.0


def sense(cell: Cell, world: World) -> dict[Sensor, float]:
    """Whitepaper section 13.1: read enabled sensors and pay for each one."""
    obs: dict[Sensor, float] = {}
    cost = world.config.physics.sense_cost
    for sensor in cell.genome.enabled_sensors():
        obs[sensor] = read_sensor(sensor, cell, world)
        if cost:
            cell.energy -= cost
            world.ledger.spent_sensing += cost
    return obs
