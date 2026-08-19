"""Append-only event log (whitepaper sections 12.1 and 12.2).

JSONL is the default because section 11.2 requires that the same config and seed
reproduce the *same event log*, and a line-oriented text format makes that a
byte comparison rather than a schema-aware diff. Parquet is offered as an
export for large-scale analysis.
"""

from __future__ import annotations

import gzip
import json
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class EventType(str, Enum):
    BIRTH = "BIRTH"
    DEATH = "DEATH"
    ACTION = "ACTION"
    MUTATION = "MUTATION"
    RESOURCE_CHANGE = "RESOURCE_CHANGE"
    SIGNAL_EMIT = "SIGNAL_EMIT"
    FIRST_DETECTION = "FIRST_DETECTION"
    CHECKPOINT = "CHECKPOINT"
    EXTINCTION = "EXTINCTION"
    EMERGENCE_CANDIDATE = "EMERGENCE_CANDIDATE"
    METRICS = "METRICS"
    RUN_START = "RUN_START"
    RUN_END = "RUN_END"
    ACCELERATION = "ACCELERATION"


@dataclass(slots=True)
class Event:
    """Whitepaper section 12.1."""

    run_id: str
    world_id: str
    timestep: int
    event_type: EventType
    cell_id: str | None = None
    parent_id: str | None = None
    lineage_id: str | None = None
    position: tuple[int, int] | None = None
    genome_hash: str | None = None
    energy: float | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> str:
        record: dict[str, Any] = {
            "run_id": self.run_id,
            "world_id": self.world_id,
            "timestep": self.timestep,
            "event_type": self.event_type.value,
        }
        if self.cell_id is not None:
            record["cell_id"] = self.cell_id
        if self.parent_id is not None:
            record["parent_id"] = self.parent_id
        if self.lineage_id is not None:
            record["lineage_id"] = self.lineage_id
        if self.position is not None:
            record["position"] = list(self.position)
        if self.genome_hash is not None:
            record["genome_hash"] = self.genome_hash
        if self.energy is not None:
            record["energy"] = round(self.energy, 4)
        if self.payload:
            record["payload"] = self.payload
        return json.dumps(record, sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Event:
        position = data.get("position")
        return cls(
            run_id=data["run_id"],
            world_id=data["world_id"],
            timestep=int(data["timestep"]),
            event_type=EventType(data["event_type"]),
            cell_id=data.get("cell_id"),
            parent_id=data.get("parent_id"),
            lineage_id=data.get("lineage_id"),
            position=None if position is None else (int(position[0]), int(position[1])),
            genome_hash=data.get("genome_hash"),
            energy=data.get("energy"),
            payload=data.get("payload", {}),
        )


class EventLog:
    """Buffered append-only writer.

    Not thread-safe by design: one log per world, one world per worker. Sharing
    a log across workers would interleave lines non-deterministically and break
    the reproducibility requirement.
    """

    def __init__(
        self,
        path: str | Path | None,
        *,
        run_id: str,
        world_id: str,
        flush_interval: int = 2000,
        compress: bool = False,
    ) -> None:
        self.run_id = run_id
        self.world_id = world_id
        self.path = Path(path) if path is not None else None
        self.flush_interval = max(1, flush_interval)
        self.compress = compress
        self.count = 0
        self.counts_by_type: dict[str, int] = {}
        self._buffer: list[str] = []
        self._handle = None
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            opener = gzip.open if compress else open
            self._handle = opener(self.path, "wt", encoding="utf-8")

    # -- writing --------------------------------------------------------------

    def emit(
        self,
        event_type: EventType,
        timestep: int,
        **kwargs: Any,
    ) -> Event:
        event = Event(
            run_id=self.run_id,
            world_id=self.world_id,
            timestep=timestep,
            event_type=event_type,
            **kwargs,
        )
        self.append(event)
        return event

    def append(self, event: Event) -> None:
        self.count += 1
        key = event.event_type.value
        self.counts_by_type[key] = self.counts_by_type.get(key, 0) + 1
        if self._handle is None:
            return
        self._buffer.append(event.to_json())
        if len(self._buffer) >= self.flush_interval:
            self.flush()

    def flush(self) -> None:
        if self._handle is None or not self._buffer:
            return
        self._handle.write("\n".join(self._buffer))
        self._handle.write("\n")
        self._handle.flush()
        self._buffer.clear()

    def close(self) -> None:
        self.flush()
        if self._handle is not None:
            self._handle.close()
            self._handle = None

    def __enter__(self) -> EventLog:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def read_events(path: str | Path) -> Iterator[Event]:
    """Stream events back out of a JSONL(.gz) log."""
    path = Path(path)
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield Event.from_dict(json.loads(line))


def export_parquet(jsonl_path: str | Path, parquet_path: str | Path) -> bool:
    """Convert a JSONL log to Parquet. Returns False if pyarrow is absent."""
    try:
        import pyarrow as pa
        import pyarrow.parquet as pq
    except ImportError:
        return False

    rows: list[dict[str, Any]] = []
    for event in read_events(jsonl_path):
        rows.append(
            {
                "run_id": event.run_id,
                "world_id": event.world_id,
                "timestep": event.timestep,
                "event_type": event.event_type.value,
                "cell_id": event.cell_id,
                "parent_id": event.parent_id,
                "lineage_id": event.lineage_id,
                "x": None if event.position is None else event.position[0],
                "y": None if event.position is None else event.position[1],
                "genome_hash": event.genome_hash,
                "energy": event.energy,
                "payload": json.dumps(event.payload, sort_keys=True) if event.payload else None,
            }
        )
    Path(parquet_path).parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.Table.from_pylist(rows), parquet_path)
    return True
