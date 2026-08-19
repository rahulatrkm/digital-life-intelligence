"""Mutation operators (whitepaper section 6.5).

Invariant 4.3: mutation must not access future information or evaluator data.
Nothing in this module can see fitness, metrics or the world -- it only sees the
parent genome and a controlled random stream.
"""

from __future__ import annotations

from dataclasses import dataclass

from worldzero.core.config import MutationConfig
from worldzero.core.types import ActionType, Direction
from worldzero.genome.gene import (
    SENSOR_RANGE,
    Comparator,
    Gene,
    Genome,
    WriteExpr,
    actions_for_stage,
    random_gene,
    sensors_for_stage,
)


@dataclass(slots=True)
class MutationRecord:
    kind: str
    gene_index: int
    detail: str = ""


@dataclass(slots=True)
class MutationResult:
    genome: Genome
    records: list[MutationRecord]
    registers: int


def mutate(
    genome: Genome,
    rng,
    config: MutationConfig,
    *,
    max_stage: int,
    registers: int,
    channels: int,
) -> MutationResult:
    """Apply the operator set once to a copied genome.

    Returns the parent genome object unchanged when mutation is disabled, which
    is what makes the zero-mutation control an exact clone lineage.
    """
    if not config.enabled:
        return MutationResult(genome, [], registers)

    genes = list(genome.genes)
    records: list[MutationRecord] = []
    sensors = sensors_for_stage(max_stage, registers, channels)
    actions = actions_for_stage(max_stage)

    # Memory expansion first: a wider register file changes what later operators
    # are allowed to reference.
    if registers < config.max_registers and rng.random() < config.memory_expansion_rate:
        registers += 1
        sensors = sensors_for_stage(max_stage, registers, channels)
        records.append(MutationRecord("memory_expansion", -1, f"registers={registers}"))

    for index in range(len(genes)):
        if rng.random() < config.point_rate:
            genes[index] = _point_mutate(genes[index], rng, registers)
            records.append(MutationRecord("point", index))
        if rng.random() < config.sensor_rate:
            genes[index] = _sensor_mutate(genes[index], rng, sensors)
            records.append(MutationRecord("sensor", index))
        if rng.random() < config.action_rate:
            genes[index] = _action_mutate(genes[index], rng, actions, registers, channels)
            records.append(MutationRecord("action", index))

    if len(genes) > 1 and rng.random() < config.priority_swap_rate:
        a, b = rng.randrange(len(genes)), rng.randrange(len(genes))
        if a != b:
            genes[a], genes[b] = (
                genes[a].replace(priority=genes[b].priority),
                genes[b].replace(priority=genes[a].priority),
            )
            records.append(MutationRecord("priority_swap", a, f"with={b}"))

    if len(genes) < config.max_genome_length and rng.random() < config.duplication_rate:
        source = rng.randrange(len(genes)) if genes else -1
        if source >= 0:
            copy = genes[source]
            if rng.random() < 0.5:
                copy = _point_mutate(copy, rng, registers)
            genes.insert(source + 1, copy)
            records.append(MutationRecord("duplication", source))

    if len(genes) < config.max_genome_length and rng.random() < config.insertion_rate:
        position = rng.randrange(len(genes) + 1)
        genes.insert(
            position,
            random_gene(
                rng, sensors=sensors, actions=actions, registers=registers, channels=channels
            ),
        )
        records.append(MutationRecord("insertion", position))

    if len(genes) > config.min_genome_length and rng.random() < config.deletion_rate:
        position = rng.randrange(len(genes))
        genes.pop(position)
        records.append(MutationRecord("deletion", position))

    if not records:
        return MutationResult(genome, [], registers)
    return MutationResult(Genome(genes), records, registers)


def _point_mutate(gene: Gene, rng, registers: int) -> Gene:
    """Perturb one continuous or index-valued field, leaving structure intact."""
    choice = rng.randrange(5)
    if choice == 0:
        low, high = SENSOR_RANGE[gene.sensor_id]
        span = (high - low) or 1.0
        value = gene.threshold + rng.gauss(0.0, span * 0.1)
        return gene.replace(threshold=max(low, min(high, value)))
    if choice == 1:
        return gene.replace(comparator=Comparator(rng.randrange(len(Comparator))))
    if choice == 2:
        return gene.replace(action_parameter=max(0.0, gene.action_parameter + rng.gauss(0.0, 0.3)))
    if choice == 3:
        if registers == 0:
            return gene
        field = "memory_read_index" if rng.random() < 0.5 else "memory_write_index"
        if rng.random() < 0.25:
            return gene.replace(**{field: None})
        new = gene.replace(**{field: rng.randrange(registers)})
        if field == "memory_write_index" and new.write_value_expression is WriteExpr.NONE:
            new = new.replace(write_value_expression=WriteExpr(rng.randrange(1, len(WriteExpr))))
        return new
    if gene.action is ActionType.MOVE:
        return gene.replace(direction=Direction(rng.randrange(4)))
    return gene.replace(priority=max(0, gene.priority + rng.choice((-2, -1, 1, 2))))


def _sensor_mutate(gene: Gene, rng, sensors: list) -> Gene:
    """Repoint a gene at a different sensor, rescaling the threshold.

    Keeping the raw threshold would almost always produce a dead gene because
    sensor ranges differ by orders of magnitude (age 0..1000 vs resource 0..10),
    so the relative position within the range is preserved instead.
    """
    if not sensors:
        return gene
    new_sensor = rng.choice(sensors)
    old_low, old_high = SENSOR_RANGE[gene.sensor_id]
    new_low, new_high = SENSOR_RANGE[new_sensor]
    old_span = (old_high - old_low) or 1.0
    fraction = (gene.threshold - old_low) / old_span
    fraction = min(1.0, max(0.0, fraction))
    return gene.replace(
        sensor_id=new_sensor,
        threshold=new_low + fraction * (new_high - new_low),
    )


def _action_mutate(gene: Gene, rng, actions: tuple, registers: int, channels: int) -> Gene:
    action = rng.choice(actions)
    updates: dict = {"action": action}
    if action is ActionType.MOVE:
        updates["direction"] = Direction(rng.randrange(4))
    else:
        updates["direction"] = None
    if action is ActionType.EMIT and channels > 0:
        updates["channel"] = rng.randrange(channels)
    if action in (ActionType.WRITE_MEMORY, ActionType.PROBE) and registers > 0:
        if gene.memory_write_index is None:
            updates["memory_write_index"] = rng.randrange(registers)
        if gene.write_value_expression is WriteExpr.NONE:
            updates["write_value_expression"] = WriteExpr(rng.randrange(1, len(WriteExpr)))
    return gene.replace(**updates)
