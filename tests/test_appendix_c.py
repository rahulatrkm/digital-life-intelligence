"""Whitepaper Appendix C: the ten first unit tests, in the order given.

These are the acceptance tests for the deterministic kernel (section 18.1). Each
test name states the Appendix C line it implements.
"""

from __future__ import annotations

from worldzero.core.config import MutationConfig, SimulationConfig
from worldzero.core.types import Action, ActionType, DeathReason, Decision, Direction
from worldzero.core.world import World
from worldzero.genome.mutation import mutate
from worldzero.storage.events import EventLog, EventType


# 1. Cell energy decreases after movement.
def test_energy_decreases_after_movement(empty_world: World, place_cell) -> None:
    cell = place_cell(empty_world)
    before = cell.energy

    decision = Decision(Action(type=ActionType.MOVE, direction=Direction.NORTH))
    empty_world.apply_cost(cell, decision)

    assert cell.energy == before - empty_world.config.physics.move_cost
    assert empty_world.ledger.spent_moving == empty_world.config.physics.move_cost


def test_movement_changes_position(empty_world: World, place_cell) -> None:
    cell = place_cell(empty_world, x=4, y=4)
    decision = Decision(Action(type=ActionType.MOVE, direction=Direction.NORTH))

    empty_world.apply_action(cell, decision, {})

    dx, dy = Direction.NORTH.delta
    assert (cell.x, cell.y) == empty_world.wrap(4 + dx, 4 + dy)
    assert empty_world.occupancy[(cell.x, cell.y)] == cell.id
    assert (4, 4) not in empty_world.occupancy


# 2. Cell dies when energy reaches zero.
def test_cell_dies_when_energy_reaches_zero(empty_world: World, place_cell) -> None:
    cell = place_cell(empty_world)

    assert empty_world.should_die(cell) is None

    cell.energy = 0.0
    assert empty_world.should_die(cell) is DeathReason.STARVATION

    empty_world.kill(cell, DeathReason.STARVATION)
    assert not cell.alive
    assert cell.death_reason is DeathReason.STARVATION
    assert (cell.x, cell.y) not in empty_world.occupancy


def test_death_reasons_cover_integrity_and_age(empty_world: World, place_cell) -> None:
    cell = place_cell(empty_world)

    cell.integrity = 0.0
    assert empty_world.should_die(cell) is DeathReason.INTEGRITY

    cell.integrity = 1.0
    cell.age = empty_world.config.physics.max_age + 1
    assert empty_world.should_die(cell) is DeathReason.OLD_AGE


# 3. Cell consumes resource and increases energy.
def test_consume_resource_increases_energy(empty_world: World, place_cell) -> None:
    cell = place_cell(empty_world, x=6, y=6, energy=10.0)
    physics = empty_world.config.physics
    empty_world.resource[6, 6] = 1.0

    decision = Decision(Action(type=ActionType.CONSUME, amount=physics.max_consume_per_step))
    empty_world.apply_action(cell, decision, {})

    expected_gain = physics.max_consume_per_step * physics.consume_rate
    assert cell.energy == 10.0 + expected_gain
    assert empty_world.resource[6, 6] == 0.0
    assert empty_world.ledger.harvested == expected_gain


def test_consume_on_empty_tile_is_a_no_op(empty_world: World, place_cell) -> None:
    cell = place_cell(empty_world, x=6, y=6, energy=10.0)
    empty_world.resource[6, 6] = 0.0

    empty_world.apply_action(cell, Decision(Action(type=ActionType.CONSUME, amount=1.0)), {})

    assert cell.energy == 10.0
    assert empty_world.ledger.harvested == 0.0


# 4. Cell divides only above reproduction threshold.
def test_divides_only_above_reproduction_threshold(empty_world: World, place_cell) -> None:
    threshold = empty_world.config.physics.reproduction_threshold
    cell = place_cell(empty_world, energy=threshold - 1.0)

    assert not empty_world.can_reproduce(cell)

    cell.energy = threshold + 1.0
    assert empty_world.can_reproduce(cell)


def test_reproduction_splits_energy_and_links_lineage(empty_world: World, place_cell) -> None:
    fraction = empty_world.config.physics.child_energy_fraction
    parent = place_cell(empty_world, energy=100.0)

    child = empty_world.spawn_child(parent)

    assert child is not None
    assert child.energy == 100.0 * fraction
    assert parent.energy == 100.0 * (1.0 - fraction)
    assert child.parent_id == parent.id
    assert child.lineage_id == parent.lineage_id
    assert child.generation == parent.generation + 1
    assert child.age == 0
    assert empty_world.births == 1


def test_no_reproduction_control_blocks_division(config: SimulationConfig, place_cell) -> None:
    world = World(config.merged({"controls": {"disable_reproduction": True}}), populate=False)
    cell = place_cell(world, energy=200.0)

    assert not world.can_reproduce(cell)


# 5. Child genome equals parent genome when mutation rate is zero.
def test_child_genome_equals_parent_when_mutation_rate_is_zero(
    empty_world: World, place_cell
) -> None:
    parent = place_cell(empty_world)
    zeroed = MutationConfig(
        point_rate=0.0,
        insertion_rate=0.0,
        deletion_rate=0.0,
        duplication_rate=0.0,
        priority_swap_rate=0.0,
        sensor_rate=0.0,
        action_rate=0.0,
        memory_expansion_rate=0.0,
    )

    for trial in range(25):
        result = mutate(
            parent.genome,
            empty_world.rng.local("zero-mutation", trial),
            zeroed,
            max_stage=0,
            registers=4,
            channels=2,
        )
        assert result.genome.hash == parent.genome.hash
        assert result.records == []


def test_disabled_mutation_clones_exactly(empty_world: World, place_cell) -> None:
    parent = place_cell(empty_world)
    result = mutate(
        parent.genome,
        empty_world.rng.local("disabled"),
        MutationConfig(enabled=False),
        max_stage=0,
        registers=4,
        channels=2,
    )
    assert result.genome is parent.genome


# 6. Child genome differs statistically when mutation rate is nonzero.
def test_child_genome_differs_when_mutation_rate_is_nonzero(
    empty_world: World, place_cell
) -> None:
    parent = place_cell(empty_world)
    hot = MutationConfig(
        point_rate=0.5,
        insertion_rate=0.2,
        deletion_rate=0.2,
        duplication_rate=0.2,
        priority_swap_rate=0.2,
        sensor_rate=0.3,
        action_rate=0.3,
    )

    trials = 60
    changed = 0
    for trial in range(trials):
        result = mutate(
            parent.genome,
            empty_world.rng.local("hot-mutation", trial),
            hot,
            max_stage=0,
            registers=4,
            channels=2,
        )
        if result.genome.hash != parent.genome.hash:
            changed += 1

    # Statistical, not absolute: a single draw may legitimately produce no change.
    assert changed > trials * 0.5, f"only {changed}/{trials} offspring differed"


# 7. Same seed and config reproduce identical event log.
def test_same_seed_and_config_reproduce_identical_event_log(config, tmp_path) -> None:
    logged = config.merged({"logging": {"log_mutations": True, "log_signals": True}})

    def run(path) -> str:
        # Identical run_id and world_id: the identity fields are not what is
        # under test, the sequence of events is.
        log = EventLog(path, run_id="fixed-run", world_id="fixed-world", flush_interval=1)
        world = World(logged, run_id="fixed-run", world_id="fixed-world", event_log=log)
        for _ in range(120):
            world.step()
        log.emit(EventType.RUN_END, world.timestep, payload=world.stats())
        log.close()
        return path.read_text(encoding="utf-8")

    first = run(tmp_path / "a.jsonl")
    second = run(tmp_path / "b.jsonl")

    assert first == second
    assert first.count("\n") > 1


def test_different_seeds_diverge(config, tmp_path) -> None:
    def run(path, seed: int) -> str:
        cfg = config.with_seed(seed)
        log = EventLog(path, run_id="r", world_id="w", flush_interval=1)
        world = World(cfg, run_id="r", world_id="w", event_log=log)
        for _ in range(60):
            world.step()
        log.close()
        return path.read_text(encoding="utf-8")

    assert run(tmp_path / "s1.jsonl", 1) != run(tmp_path / "s2.jsonl", 2)


# 8. Signal decays after configured TTL.
def test_signal_decays_after_configured_ttl(empty_world: World, place_cell) -> None:
    cell = place_cell(empty_world)
    ttl = empty_world.config.physics.signal_ttl

    empty_world.emit_signal(cell, channel=0, value=1.0)
    assert len(empty_world.signals) == 1

    for _ in range(ttl - 1):
        empty_world.decay_signals()
    assert empty_world.signals, "signal expired before its TTL elapsed"

    empty_world.decay_signals()
    assert empty_world.signals == []
    assert not empty_world.signal_field.any()


def test_signal_value_attenuates_each_step(empty_world: World, place_cell) -> None:
    cell = place_cell(empty_world)
    decay = empty_world.config.physics.signal_decay

    empty_world.emit_signal(cell, channel=0, value=1.0)
    empty_world.decay_signals()

    assert empty_world.signals[0].value == 1.0 * decay


def test_emit_rejects_out_of_range_channel(empty_world: World, place_cell) -> None:
    cell = place_cell(empty_world)
    empty_world.emit_signal(cell, channel=99, value=1.0)
    assert empty_world.signals == []


# 9. Memory registers change only through allowed actions.
def test_memory_registers_change_only_through_allowed_actions(
    empty_world: World, place_cell
) -> None:
    cell = place_cell(empty_world)
    assert cell.internal_state == [0.0] * len(cell.internal_state)

    empty_world.write_memory(cell, 1, 3.5)
    assert cell.internal_state[1] == 3.5

    # Out-of-range indices are ignored rather than raising or wrapping.
    empty_world.write_memory(cell, len(cell.internal_state) + 5, 9.0)
    empty_world.write_memory(cell, -1, 9.0)
    assert 9.0 not in cell.internal_state

    # A non-memory action leaves the register file untouched.
    before = list(cell.internal_state)
    move = Decision(Action(type=ActionType.MOVE, direction=Direction.EAST))
    empty_world.apply_action(cell, move, {})
    assert cell.internal_state == before


def test_no_memory_control_freezes_registers(config: SimulationConfig, place_cell) -> None:
    world = World(config.merged({"controls": {"disable_memory": True}}), populate=False)
    cell = place_cell(world)

    world.write_memory(cell, 0, 42.0)

    assert cell.internal_state[0] == 0.0


def test_memory_writes_are_clamped(empty_world: World, place_cell) -> None:
    cell = place_cell(empty_world)
    empty_world.write_memory(cell, 0, 1e12)
    assert abs(cell.internal_state[0]) <= 1e6


# 10. Lineage tree has no orphan child except initial ancestors.
def test_lineage_tree_has_no_orphans(world: World) -> None:
    for _ in range(150):
        world.step()

    assert not world.lineage.has_orphans()


def test_every_cell_links_to_a_parent_or_is_a_founder(world: World) -> None:
    for _ in range(150):
        world.step()

    for cell in world.cells.values():
        if cell.generation == 0:
            assert cell.parent_id is None
        else:
            assert cell.parent_id is not None
            assert cell.lineage_id
