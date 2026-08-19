"""Gene evaluation (whitepaper section 6.4).

    for gene in genome sorted by priority:
        if gene_condition_matches(gene, obs, cell.internal_state):
            candidate_actions.append(gene.action)
    action = choose_first_valid(candidate_actions) or STAY

Validity is checked against the world rather than assumed, so a genome that
keeps trying to walk into a wall pays the idle cost and gets nothing -- the
tradeoff the physics rules are supposed to create.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from worldzero.core.types import Action, ActionType, Cell, Decision, Direction, MemoryWrite
from worldzero.genome.gene import Gene, WriteExpr
from worldzero.genome.sensors import sense

if TYPE_CHECKING:  # pragma: no cover
    from worldzero.core.world import World

__all__ = ["decide", "gene_condition_matches", "sense"]

_STAY = Action(ActionType.STAY)


def gene_condition_matches(gene: Gene, obs: dict, internal_state: list[float]) -> bool:
    """Sensor comparison, optionally gated on a memory register being positive."""
    value = obs.get(gene.sensor_id)
    if value is None:
        return False
    if not gene.comparator.apply(value, gene.threshold):
        return False
    read = gene.memory_read_index
    if read is not None:
        if read >= len(internal_state):
            return False
        if internal_state[read] <= 0.0:
            return False
    return True


def build_action(gene: Gene, cell: Cell, world: World) -> Action:
    kind = gene.action
    if kind is ActionType.MOVE:
        direction = gene.direction if gene.direction is not None else Direction.NORTH
        return Action(ActionType.MOVE, direction=direction)
    if kind is ActionType.CONSUME:
        cap = world.config.physics.max_consume_per_step
        return Action(ActionType.CONSUME, amount=min(cap, max(0.0, gene.action_parameter) * cap))
    if kind is ActionType.EMIT:
        return Action(ActionType.EMIT, channel=gene.channel, value=gene.action_parameter)
    if kind is ActionType.WRITE_MEMORY:
        index = gene.memory_write_index if gene.memory_write_index is not None else 0
        return Action(
            ActionType.WRITE_MEMORY,
            index=index,
            value=evaluate_write(gene, cell, world),
        )
    if kind is ActionType.ALTER_TILE:
        return Action(ActionType.ALTER_TILE, value=gene.action_parameter)
    if kind is ActionType.PROBE:
        index = gene.memory_write_index if gene.memory_write_index is not None else 0
        return Action(ActionType.PROBE, index=index)
    if kind is ActionType.DIVIDE:
        return Action(ActionType.DIVIDE)
    return Action(ActionType.STAY)


def evaluate_write(gene: Gene, cell: Cell, world: World) -> float:
    """Resolve ``write_value_expression`` into a concrete register value."""
    expr = gene.write_value_expression
    index = gene.memory_write_index
    current = 0.0
    if index is not None and index < len(cell.internal_state):
        current = cell.internal_state[index]

    if expr is WriteExpr.SET_ZERO:
        return 0.0
    if expr is WriteExpr.SET_ONE:
        return 1.0
    if expr is WriteExpr.SET_CONSTANT:
        return gene.action_parameter
    if expr is WriteExpr.COPY_SENSOR:
        return world.last_observation.get(gene.sensor_id, 0.0)
    if expr is WriteExpr.INCREMENT:
        return current + 1.0
    if expr is WriteExpr.DECREMENT:
        return current - 1.0
    if expr is WriteExpr.TOGGLE:
        return 0.0 if current > 0.0 else 1.0
    if expr is WriteExpr.DECAY:
        return current * 0.5
    return current


def is_valid(action: Action, cell: Cell, world: World) -> bool:
    kind = action.type
    if kind is ActionType.MOVE:
        assert action.direction is not None
        dx, dy = action.direction.delta
        nx, ny = world.wrap(cell.x + dx, cell.y + dy)
        return nx >= 0 and world.is_free(nx, ny)
    if kind is ActionType.CONSUME:
        return world.resource[cell.y, cell.x] > 1e-9
    if kind is ActionType.EMIT:
        return (
            world.config.physics.signal_channels > action.channel >= 0
            and cell.energy > world.config.physics.signal_cost
        )
    if kind is ActionType.WRITE_MEMORY:
        return 0 <= action.index < len(cell.internal_state)
    if kind is ActionType.DIVIDE:
        return world.can_reproduce(cell)
    if kind is ActionType.PROBE:
        return (
            not world.config.controls.disable_probe
            and cell.energy > world.config.physics.probe_cost
            and 0 <= action.index < len(cell.internal_state)
        )
    if kind is ActionType.ALTER_TILE:
        return (
            not world.config.controls.disable_markers
            and cell.energy > world.config.physics.alter_tile_cost
        )
    return True


def decide(cell: Cell, obs: dict, world: World) -> Decision:
    """Return the first valid action the rule table proposes, else STAY."""
    if world.config.controls.random_actions:
        return _random_decision(cell, world)

    world.last_observation = obs
    fallback: Decision | None = None

    for position, gene in enumerate(cell.genome.ordered()):
        if not gene_condition_matches(gene, obs, cell.internal_state):
            continue
        action = build_action(gene, cell, world)
        write = _pending_write(gene, cell, world)
        decision = Decision(action=action, write=write, gene_index=position)
        if is_valid(action, cell, world):
            return decision
        if fallback is None and write is not None:
            # The action was impossible but the gene still fired; keep its memory
            # write so that "I tried and failed" can become storable information.
            fallback = Decision(action=Action(ActionType.STAY), write=write, gene_index=position)

    return fallback if fallback is not None else Decision(action=Action(ActionType.STAY))


def _pending_write(gene: Gene, cell: Cell, world: World) -> MemoryWrite | None:
    if gene.action is ActionType.WRITE_MEMORY:
        return None  # the action itself performs the write
    index = gene.memory_write_index
    if index is None or gene.write_value_expression is WriteExpr.NONE:
        return None
    if index >= len(cell.internal_state):
        return None
    return MemoryWrite(index=index, value=evaluate_write(gene, cell, world))


def _random_decision(cell: Cell, world: World) -> Decision:
    """Non-adaptive baseline (section 17): behaviour independent of genome and senses."""
    rng = world.rng.local("random-control", world.timestep, cell.id)
    choices = (ActionType.STAY, ActionType.MOVE, ActionType.CONSUME, ActionType.DIVIDE)
    kind = rng.choice(choices)
    if kind is ActionType.MOVE:
        action = Action(ActionType.MOVE, direction=Direction(rng.randrange(4)))
    elif kind is ActionType.CONSUME:
        action = Action(ActionType.CONSUME, amount=world.config.physics.max_consume_per_step)
    else:
        action = Action(kind)
    if not is_valid(action, cell, world):
        action = Action(ActionType.STAY)
    return Decision(action=action)
