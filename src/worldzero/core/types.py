"""Core value types: cells, actions, signals (whitepaper sections 4 and 6.3)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Any


class Direction(IntEnum):
    NORTH = 0
    SOUTH = 1
    EAST = 2
    WEST = 3

    @property
    def delta(self) -> tuple[int, int]:
        return _DELTAS[self]


_DELTAS: dict[Direction, tuple[int, int]] = {
    Direction.NORTH: (0, -1),
    Direction.SOUTH: (0, 1),
    Direction.EAST: (1, 0),
    Direction.WEST: (-1, 0),
}


class ActionType(IntEnum):
    """Whitepaper section 6.3.

    ``PROBE`` is the costly information-gathering intervention required by the
    scientific-behaviour experiments (sections 14.7 and 18.5); ``ALTER_TILE``
    is the environment-modification action that gives culture something to be
    written onto.
    """

    STAY = 0
    MOVE = 1
    CONSUME = 2
    EMIT = 3
    WRITE_MEMORY = 4
    DIVIDE = 5
    ALTER_TILE = 6
    PROBE = 7


class DeathReason(IntEnum):
    STARVATION = 0
    INTEGRITY = 1
    OLD_AGE = 2
    LETHAL_EVENT = 3


@dataclass(slots=True)
class Action:
    """A single decided action plus whichever parameters its type needs."""

    type: ActionType = ActionType.STAY
    direction: Direction | None = None
    channel: int = 0
    value: float = 0.0
    index: int = 0
    amount: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type.name,
            "direction": None if self.direction is None else self.direction.name,
            "channel": self.channel,
            "value": round(self.value, 6),
            "index": self.index,
            "amount": round(self.amount, 6),
        }


@dataclass(slots=True)
class MemoryWrite:
    """A pending write to an internal register, produced by a firing gene."""

    index: int
    value: float


@dataclass(slots=True)
class Decision:
    """What a genome produced this step: one action, optionally one memory write."""

    action: Action
    write: MemoryWrite | None = None
    gene_index: int = -1


@dataclass(slots=True)
class Signal:
    """A local deposit on a signalling channel (whitepaper section 6.3, EMIT)."""

    x: int
    y: int
    channel: int
    value: float
    ttl: int
    emitter_id: str
    emitted_at: int


@dataclass(slots=True)
class Cell:
    """Whitepaper section 4.1.

    Field order and names follow the paper so the formal spec and the code can
    be diffed by eye.
    """

    id: str
    lineage_id: str
    parent_id: str | None
    generation: int
    x: int
    y: int
    energy: float
    age: int
    integrity: float
    genome: Any  # worldzero.genome.gene.Genome; untyped here to avoid a cycle
    internal_state: list[float] = field(default_factory=list)
    last_action: Action | None = None
    alive: bool = True
    birth_step: int = 0
    death_step: int | None = None
    death_reason: DeathReason | None = None
    offspring_count: int = 0
    energy_consumed: float = 0.0
    signals_emitted: int = 0
    probes_performed: int = 0

    @property
    def position(self) -> tuple[int, int]:
        return (self.x, self.y)

    def lifespan(self, now: int) -> int:
        end = self.death_step if self.death_step is not None else now
        return max(0, end - self.birth_step)

    def summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "lineage_id": self.lineage_id,
            "parent_id": self.parent_id,
            "generation": self.generation,
            "x": self.x,
            "y": self.y,
            "energy": round(self.energy, 4),
            "age": self.age,
            "integrity": round(self.integrity, 4),
            "alive": self.alive,
            "genome_hash": self.genome.hash if self.genome is not None else None,
        }


def new_cell_id(rng_stream: Any) -> str:
    """Deterministic UUID4-shaped identifier.

    :func:`uuid.uuid4` reads ``os.urandom`` and would break run reproducibility,
    so the 128 bits come from a controlled stream instead.
    """
    return str(uuid.UUID(int=rng_stream.getrandbits(128), version=4))
