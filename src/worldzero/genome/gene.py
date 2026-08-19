"""Rule-table genome (whitepaper section 6.1).

The paper is explicit that a rule table should come before neural or program
genomes: it is transparent, cheap to mutate and directly auditable, which
matters because the emergence detectors have to be able to point at *why* a
behaviour counts.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from enum import IntEnum
from typing import Any

from worldzero.core.types import ActionType, Direction


class Comparator(IntEnum):
    LT = 0
    LE = 1
    GT = 2
    GE = 3
    EQ = 4

    def apply(self, left: float, right: float) -> bool:
        if self is Comparator.LT:
            return left < right
        if self is Comparator.LE:
            return left <= right
        if self is Comparator.GT:
            return left > right
        if self is Comparator.GE:
            return left >= right
        return abs(left - right) < 1e-9


class Sensor(IntEnum):
    """Whitepaper section 6.2. Stage gating lives in :data:`SENSOR_STAGE`."""

    RESOURCE_HERE = 0
    RESOURCE_GRADIENT_NORTH = 1
    RESOURCE_GRADIENT_SOUTH = 2
    RESOURCE_GRADIENT_EAST = 3
    RESOURCE_GRADIENT_WEST = 4
    HAZARD_HERE = 5
    ENERGY_LEVEL = 6
    AGE = 7
    HAZARD_GRADIENT_NORTH = 8
    HAZARD_GRADIENT_SOUTH = 9
    HAZARD_GRADIENT_EAST = 10
    HAZARD_GRADIENT_WEST = 11
    MEMORY_0 = 12
    MEMORY_1 = 13
    MEMORY_2 = 14
    MEMORY_3 = 15
    CUE_HERE = 16
    CELL_DENSITY = 17
    MARKER_HERE = 18
    SIGNAL_CHANNEL_0 = 19
    SIGNAL_CHANNEL_1 = 20


SENSOR_STAGE: dict[Sensor, int] = {
    Sensor.RESOURCE_HERE: 0,
    Sensor.RESOURCE_GRADIENT_NORTH: 0,
    Sensor.RESOURCE_GRADIENT_SOUTH: 0,
    Sensor.RESOURCE_GRADIENT_EAST: 0,
    Sensor.RESOURCE_GRADIENT_WEST: 0,
    Sensor.HAZARD_HERE: 0,
    Sensor.ENERGY_LEVEL: 0,
    Sensor.AGE: 0,
    Sensor.HAZARD_GRADIENT_NORTH: 1,
    Sensor.HAZARD_GRADIENT_SOUTH: 1,
    Sensor.HAZARD_GRADIENT_EAST: 1,
    Sensor.HAZARD_GRADIENT_WEST: 1,
    Sensor.MEMORY_0: 1,
    Sensor.MEMORY_1: 1,
    Sensor.MEMORY_2: 1,
    Sensor.MEMORY_3: 1,
    Sensor.CUE_HERE: 1,
    Sensor.CELL_DENSITY: 2,
    Sensor.MARKER_HERE: 2,
    Sensor.SIGNAL_CHANNEL_0: 3,
    Sensor.SIGNAL_CHANNEL_1: 3,
}

MEMORY_SENSORS: tuple[Sensor, ...] = (
    Sensor.MEMORY_0,
    Sensor.MEMORY_1,
    Sensor.MEMORY_2,
    Sensor.MEMORY_3,
)

SIGNAL_SENSORS: tuple[Sensor, ...] = (
    Sensor.SIGNAL_CHANNEL_0,
    Sensor.SIGNAL_CHANNEL_1,
)

#: Plausible comparison range per sensor, so a random threshold is not
#: guaranteed dead on arrival (a threshold of 90 on a 0..1 sensor never fires).
SENSOR_RANGE: dict[Sensor, tuple[float, float]] = {
    Sensor.RESOURCE_HERE: (0.0, 10.0),
    Sensor.RESOURCE_GRADIENT_NORTH: (-10.0, 10.0),
    Sensor.RESOURCE_GRADIENT_SOUTH: (-10.0, 10.0),
    Sensor.RESOURCE_GRADIENT_EAST: (-10.0, 10.0),
    Sensor.RESOURCE_GRADIENT_WEST: (-10.0, 10.0),
    Sensor.HAZARD_HERE: (0.0, 5.0),
    Sensor.HAZARD_GRADIENT_NORTH: (-5.0, 5.0),
    Sensor.HAZARD_GRADIENT_SOUTH: (-5.0, 5.0),
    Sensor.HAZARD_GRADIENT_EAST: (-5.0, 5.0),
    Sensor.HAZARD_GRADIENT_WEST: (-5.0, 5.0),
    Sensor.ENERGY_LEVEL: (0.0, 200.0),
    Sensor.AGE: (0.0, 1000.0),
    Sensor.CELL_DENSITY: (0.0, 8.0),
    Sensor.CUE_HERE: (0.0, 2.0),
    Sensor.MARKER_HERE: (0.0, 5.0),
    Sensor.MEMORY_0: (-4.0, 4.0),
    Sensor.MEMORY_1: (-4.0, 4.0),
    Sensor.MEMORY_2: (-4.0, 4.0),
    Sensor.MEMORY_3: (-4.0, 4.0),
    Sensor.SIGNAL_CHANNEL_0: (0.0, 4.0),
    Sensor.SIGNAL_CHANNEL_1: (0.0, 4.0),
}


class WriteExpr(IntEnum):
    """``write_value_expression`` from section 6.1."""

    NONE = 0
    SET_ZERO = 1
    SET_ONE = 2
    SET_CONSTANT = 3
    COPY_SENSOR = 4
    INCREMENT = 5
    DECREMENT = 6
    TOGGLE = 7
    DECAY = 8


def sensors_for_stage(max_stage: int, registers: int = 4, channels: int = 2) -> list[Sensor]:
    """Sensors reachable by mutation given the experiment stage and cell shape."""
    out: list[Sensor] = []
    for sensor, stage in SENSOR_STAGE.items():
        if stage > max_stage:
            continue
        if sensor in MEMORY_SENSORS and MEMORY_SENSORS.index(sensor) >= registers:
            continue
        if sensor in SIGNAL_SENSORS and SIGNAL_SENSORS.index(sensor) >= channels:
            continue
        out.append(sensor)
    return sorted(out)


ACTIONS_FOR_STAGE: dict[int, tuple[ActionType, ...]] = {
    0: (ActionType.STAY, ActionType.MOVE, ActionType.CONSUME, ActionType.DIVIDE),
    1: (
        ActionType.STAY,
        ActionType.MOVE,
        ActionType.CONSUME,
        ActionType.DIVIDE,
        ActionType.WRITE_MEMORY,
    ),
    2: (
        ActionType.STAY,
        ActionType.MOVE,
        ActionType.CONSUME,
        ActionType.DIVIDE,
        ActionType.WRITE_MEMORY,
        ActionType.ALTER_TILE,
        ActionType.PROBE,
    ),
    3: (
        ActionType.STAY,
        ActionType.MOVE,
        ActionType.CONSUME,
        ActionType.DIVIDE,
        ActionType.WRITE_MEMORY,
        ActionType.ALTER_TILE,
        ActionType.PROBE,
        ActionType.EMIT,
    ),
}


def actions_for_stage(max_stage: int) -> tuple[ActionType, ...]:
    return ACTIONS_FOR_STAGE[max(0, min(3, max_stage))]


@dataclass(slots=True, frozen=True)
class Gene:
    """Whitepaper section 6.1.

    ``memory_read_index`` acts as a guard: when set, the gene fires only if that
    register is positive. That is what lets a register become causally load
    bearing rather than decorative, which the memory detector needs.
    """

    sensor_id: Sensor
    comparator: Comparator
    threshold: float
    action: ActionType
    action_parameter: float = 0.0
    direction: Direction | None = None
    channel: int = 0
    memory_read_index: int | None = None
    memory_write_index: int | None = None
    write_value_expression: WriteExpr = WriteExpr.NONE
    priority: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "sensor_id": self.sensor_id.name,
            "comparator": self.comparator.name,
            "threshold": round(self.threshold, 6),
            "action": self.action.name,
            "action_parameter": round(self.action_parameter, 6),
            "direction": None if self.direction is None else self.direction.name,
            "channel": self.channel,
            "memory_read_index": self.memory_read_index,
            "memory_write_index": self.memory_write_index,
            "write_value_expression": self.write_value_expression.name,
            "priority": self.priority,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Gene:
        return cls(
            sensor_id=Sensor[data["sensor_id"]],
            comparator=Comparator[data["comparator"]],
            threshold=float(data["threshold"]),
            action=ActionType[data["action"]],
            action_parameter=float(data.get("action_parameter", 0.0)),
            direction=None if data.get("direction") is None else Direction[data["direction"]],
            channel=int(data.get("channel", 0)),
            memory_read_index=data.get("memory_read_index"),
            memory_write_index=data.get("memory_write_index"),
            write_value_expression=WriteExpr[data.get("write_value_expression", "NONE")],
            priority=int(data.get("priority", 0)),
        )

    def canonical(self) -> str:
        return (
            f"{self.sensor_id.value}|{self.comparator.value}|{self.threshold:.6f}|"
            f"{self.action.value}|{self.action_parameter:.6f}|"
            f"{-1 if self.direction is None else self.direction.value}|{self.channel}|"
            f"{-1 if self.memory_read_index is None else self.memory_read_index}|"
            f"{-1 if self.memory_write_index is None else self.memory_write_index}|"
            f"{self.write_value_expression.value}|{self.priority}"
        )

    def replace(self, **changes: Any) -> Gene:
        return replace(self, **changes)


class Genome:
    """An ordered rule table.

    Genes are kept sorted by descending priority; ties keep insertion order so
    that a duplicated gene sits next to its parent and mutation of ordering is
    an explicit operator rather than an accident of sorting.
    """

    __slots__ = ("_genes", "_hash", "_sensors")

    def __init__(self, genes: list[Gene] | tuple[Gene, ...] = ()) -> None:
        self._genes: tuple[Gene, ...] = tuple(genes)
        self._hash: str | None = None
        self._sensors: tuple[Sensor, ...] | None = None

    @property
    def genes(self) -> tuple[Gene, ...]:
        return self._genes

    def __len__(self) -> int:
        return len(self._genes)

    def __iter__(self):
        return iter(self._genes)

    def __getitem__(self, index: int) -> Gene:
        return self._genes[index]

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Genome) and other._genes == self._genes

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Genome(len={len(self._genes)}, hash={self.hash[:8]})"

    def ordered(self) -> tuple[Gene, ...]:
        """Genes in evaluation order (section 6.4: 'sorted by priority')."""
        return tuple(sorted(self._genes, key=lambda g: -g.priority))

    def enabled_sensors(self) -> tuple[Sensor, ...]:
        """Only sensors a gene actually references are read, and paid for."""
        if self._sensors is None:
            seen: dict[Sensor, None] = {}
            for gene in self._genes:
                seen.setdefault(gene.sensor_id, None)
            self._sensors = tuple(seen)
        return self._sensors

    @property
    def hash(self) -> str:
        if self._hash is None:
            blob = ";".join(g.canonical() for g in self._genes)
            self._hash = hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]
        return self._hash

    def uses_memory(self) -> bool:
        return any(
            g.memory_read_index is not None
            or g.memory_write_index is not None
            or g.sensor_id in MEMORY_SENSORS
            for g in self._genes
        )

    def uses_signals(self) -> bool:
        return any(
            g.action is ActionType.EMIT or g.sensor_id in SIGNAL_SENSORS for g in self._genes
        )

    def complexity(self) -> dict[str, float]:
        """Structural descriptors used by the complexity-growth metric (15.1)."""
        distinct_actions = {g.action for g in self._genes}
        distinct_sensors = set(self.enabled_sensors())
        memory_genes = sum(
            1
            for g in self._genes
            if g.memory_read_index is not None or g.memory_write_index is not None
        )
        return {
            "length": float(len(self._genes)),
            "distinct_actions": float(len(distinct_actions)),
            "distinct_sensors": float(len(distinct_sensors)),
            "memory_genes": float(memory_genes),
        }

    def to_list(self) -> list[dict[str, Any]]:
        return [g.to_dict() for g in self._genes]

    @classmethod
    def from_list(cls, data: list[dict[str, Any]]) -> Genome:
        return cls([Gene.from_dict(d) for d in data])


def random_gene(
    rng: Any,
    *,
    sensors: list[Sensor],
    actions: tuple[ActionType, ...],
    registers: int,
    channels: int,
) -> Gene:
    sensor = rng.choice(sensors)
    low, high = SENSOR_RANGE[sensor]
    action = rng.choice(actions)
    use_read = registers > 0 and rng.random() < 0.15
    use_write = registers > 0 and rng.random() < 0.15
    return Gene(
        sensor_id=sensor,
        comparator=Comparator(rng.randrange(len(Comparator))),
        threshold=rng.uniform(low, high),
        action=action,
        action_parameter=rng.uniform(0.0, 2.0),
        direction=Direction(rng.randrange(4)) if action is ActionType.MOVE else None,
        channel=rng.randrange(channels) if channels > 0 else 0,
        memory_read_index=rng.randrange(registers) if use_read else None,
        memory_write_index=rng.randrange(registers) if use_write else None,
        write_value_expression=(
            WriteExpr(rng.randrange(1, len(WriteExpr))) if use_write else WriteExpr.NONE
        ),
        priority=rng.randrange(0, 32),
    )


def random_genome(
    rng: Any,
    *,
    length: int,
    max_stage: int,
    registers: int,
    channels: int,
) -> Genome:
    """A random ancestral rule table.

    Deliberately not seeded with anything useful: the whole point is that no
    resource-seeking, memory or signalling behaviour is written by hand.
    """
    sensors = sensors_for_stage(max_stage, registers, channels)
    actions = actions_for_stage(max_stage)
    return Genome(
        [
            random_gene(
                rng, sensors=sensors, actions=actions, registers=registers, channels=channels
            )
            for _ in range(length)
        ]
    )
