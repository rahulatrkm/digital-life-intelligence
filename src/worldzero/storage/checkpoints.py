"""World checkpoints (whitepaper section 12.3).

Checkpoints must round-trip exactly: section 19 asks for accelerated runs to be
re-validated against exact runs, which is only meaningful if a reloaded world
continues identically to one that never stopped.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

from worldzero.core.types import Action, ActionType, Cell, DeathReason, Direction
from worldzero.genome.gene import Genome

if TYPE_CHECKING:  # pragma: no cover
    from worldzero.core.world import World

CHECKPOINT_FORMAT = 2


def world_to_dict(world: World) -> dict[str, Any]:
    from worldzero import __version__

    return {
        "format": CHECKPOINT_FORMAT,
        "code_version": __version__,
        "run_id": world.run_id,
        "world_id": world.world_id,
        "timestep": world.timestep,
        "config": world.config.to_dict(),
        "config_fingerprint": world.config.fingerprint(),
        "rng_seed": world.rng.seed,
        "next_cell_index": world.next_cell_index,
        "grids": {
            "resource": world.resource.tolist(),
            "hazard": world.hazard.tolist(),
            "cue": world.cue.tolist(),
            "marker": world.marker.tolist(),
            "obstacle": world.obstacle.astype(np.uint8).tolist(),
            "variant": world.variant.astype(np.int16).tolist(),
            "hidden_resource": world.hidden_resource.tolist(),
        },
        "signals": [
            {
                "x": s.x,
                "y": s.y,
                "channel": s.channel,
                "value": s.value,
                "ttl": s.ttl,
                "emitter_id": s.emitter_id,
                "emitted_at": s.emitted_at,
            }
            for s in world.signals
        ],
        "cells": [_cell_to_dict(c) for c in world.cells.values()],
        "environment_state": world.environment.state(),
        "ledger": world.ledger.to_dict(),
        "lineage": world.lineage.state(),
        "rng_state": world.rng.state(),
        "counters": {
            "births": world.births,
            "deaths": world.deaths,
            "deaths_by_reason": dict(world.deaths_by_reason),
            "extinct_at": world.extinct_at,
            "probe_info_gain": world.probe_info_gain,
            "shocks": list(world.shocks),
        },
        "stats": world.stats(),
    }


def _cell_to_dict(cell: Cell) -> dict[str, Any]:
    return {
        "id": cell.id,
        "lineage_id": cell.lineage_id,
        "parent_id": cell.parent_id,
        "generation": cell.generation,
        "x": cell.x,
        "y": cell.y,
        "energy": cell.energy,
        "age": cell.age,
        "integrity": cell.integrity,
        "genome": cell.genome.to_list(),
        "internal_state": list(cell.internal_state),
        "last_action": None if cell.last_action is None else cell.last_action.to_dict(),
        "alive": cell.alive,
        "birth_step": cell.birth_step,
        "death_step": cell.death_step,
        "death_reason": None if cell.death_reason is None else cell.death_reason.name,
        "offspring_count": cell.offspring_count,
        "energy_consumed": cell.energy_consumed,
        "signals_emitted": cell.signals_emitted,
        "probes_performed": cell.probes_performed,
    }


def _cell_from_dict(data: dict[str, Any]) -> Cell:
    action_data = data.get("last_action")
    last_action = None
    if action_data:
        direction = action_data.get("direction")
        last_action = Action(
            type=ActionType[action_data["type"]],
            direction=None if direction is None else Direction[direction],
            channel=action_data.get("channel", 0),
            value=action_data.get("value", 0.0),
            index=action_data.get("index", 0),
            amount=action_data.get("amount", 0.0),
        )
    reason = data.get("death_reason")
    return Cell(
        id=data["id"],
        lineage_id=data["lineage_id"],
        parent_id=data.get("parent_id"),
        generation=data["generation"],
        x=data["x"],
        y=data["y"],
        energy=data["energy"],
        age=data["age"],
        integrity=data["integrity"],
        genome=Genome.from_list(data["genome"]),
        internal_state=list(data.get("internal_state", [])),
        last_action=last_action,
        alive=data.get("alive", True),
        birth_step=data.get("birth_step", 0),
        death_step=data.get("death_step"),
        death_reason=None if reason is None else DeathReason[reason],
        offspring_count=data.get("offspring_count", 0),
        energy_consumed=data.get("energy_consumed", 0.0),
        signals_emitted=data.get("signals_emitted", 0),
        probes_performed=data.get("probes_performed", 0),
    )


def save_checkpoint(world: World, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(world_to_dict(world), separators=(",", ":"))
    if path.suffix == ".gz":
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            handle.write(blob)
    else:
        path.write_text(blob, encoding="utf-8")
    return path


def load_checkpoint(path: str | Path, event_log=None) -> World:
    from worldzero.core.config import SimulationConfig
    from worldzero.core.types import Signal
    from worldzero.core.world import World

    path = Path(path)
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            data = json.load(handle)
    else:
        data = json.loads(path.read_text(encoding="utf-8"))

    if data.get("format") != CHECKPOINT_FORMAT:
        raise ValueError(
            f"Checkpoint format {data.get('format')} is not supported "
            f"(expected {CHECKPOINT_FORMAT})"
        )

    config = SimulationConfig.from_dict(data["config"])
    world = World(
        config,
        run_id=data["run_id"],
        world_id=data["world_id"],
        event_log=event_log,
        populate=False,
    )
    world.timestep = data["timestep"]
    world.next_cell_index = data.get("next_cell_index", 0)

    grids = data["grids"]
    world.resource = np.asarray(grids["resource"], dtype=np.float32)
    world.hazard = np.asarray(grids["hazard"], dtype=np.float32)
    world.cue = np.asarray(grids["cue"], dtype=np.float32)
    world.marker = np.asarray(grids["marker"], dtype=np.float32)
    world.obstacle = np.asarray(grids["obstacle"], dtype=np.uint8).astype(bool)
    world.variant = np.asarray(grids["variant"], dtype=np.int16)
    world.hidden_resource = np.asarray(grids["hidden_resource"], dtype=np.float32)

    world.signals = [Signal(**s) for s in data.get("signals", [])]
    # Lineage aggregates load first: register_existing increments `alive`.
    world.lineage.load_state(data.get("lineage", {}))
    for cell_data in data["cells"]:
        cell = _cell_from_dict(cell_data)
        world.cells[cell.id] = cell
        if cell.alive:
            world.occupancy[(cell.x, cell.y)] = cell.id
            world.lineage.register_existing(cell)

    counters = data.get("counters", {})
    world.births = counters.get("births", 0)
    world.deaths = counters.get("deaths", 0)
    world.deaths_by_reason = dict(counters.get("deaths_by_reason", {}))
    world.extinct_at = counters.get("extinct_at")
    world.probe_info_gain = counters.get("probe_info_gain", 0.0)
    world.shocks = list(counters.get("shocks", []))

    world.rng.load_state(data.get("rng_state", {}))
    world.ledger.load(data.get("ledger", {}))
    world.environment.restore(data.get("environment_state", {}))
    world.rebuild_signal_field()
    world.refresh_memory_pool()
    return world
