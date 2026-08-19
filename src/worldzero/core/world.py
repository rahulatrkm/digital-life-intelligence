"""The deterministic world update loop (whitepaper sections 5, 7 and 13).

The step order follows section 7.1 exactly:

    update_environment -> for each shuffled living cell:
        sense -> decide -> apply_cost -> apply_action -> update_metabolism
        -> maybe reproduce -> maybe die
    -> decay_signals -> log

Two rules keep the physics honest. Every action has a cost, delay or risk
(invariant 4.3), and every joule is attributed to a bucket in the ledger so the
energy books can be audited rather than assumed.
"""

from __future__ import annotations

import uuid
from typing import Any

import numpy as np

from worldzero.core.config import SimulationConfig
from worldzero.core.ledger import EnergyLedger
from worldzero.core.lineage import LineageTracker
from worldzero.core.rng import DeterministicRNG
from worldzero.core.types import (
    ActionType,
    Cell,
    DeathReason,
    Decision,
    Signal,
    new_cell_id,
)
from worldzero.environments import Environment
from worldzero.genome.execution import decide
from worldzero.genome.gene import Sensor, random_genome
from worldzero.genome.mutation import mutate
from worldzero.genome.sensors import sense
from worldzero.storage.events import EventLog, EventType

_NEIGHBOURS_8 = ((-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1))


class World:
    """One universe. Whitepaper section 5.1."""

    def __init__(
        self,
        config: SimulationConfig,
        *,
        run_id: str | None = None,
        world_id: str | None = None,
        event_log: EventLog | None = None,
        populate: bool = True,
        trace: Any = None,
    ) -> None:
        self.config = config
        self.run_id = run_id or f"run-{config.name}-{config.world.seed}"
        self.world_id = world_id or f"world-{config.world.seed}"
        self.rng = DeterministicRNG(config.world.seed)
        self.event_log = event_log
        self.trace = trace

        self.width = config.world.width
        self.height = config.world.height
        self.wrap_enabled = config.world.wrap
        self.timestep = 0

        shape = (self.height, self.width)
        self.resource = np.zeros(shape, dtype=np.float32)
        self.hazard = np.zeros(shape, dtype=np.float32)
        self.cue = np.zeros(shape, dtype=np.float32)
        self.marker = np.zeros(shape, dtype=np.float32)
        self.hidden_resource = np.zeros(shape, dtype=np.float32)
        self.variant = np.zeros(shape, dtype=np.int16)
        self.obstacle = np.zeros(shape, dtype=bool)

        channels = max(1, config.physics.signal_channels)
        self.signals: list[Signal] = []
        self.signal_field = np.zeros((channels, self.height, self.width), dtype=np.float32)

        self.cells: dict[str, Cell] = {}
        self.occupancy: dict[tuple[int, int], str] = {}
        self.lineage = LineageTracker()
        self.ledger = EnergyLedger()
        self.environment = Environment(config)

        self.next_cell_index = 0
        self.last_observation: dict[Sensor, float] = {}
        self.shocks: list[int] = []
        self.extinct_at: int | None = None
        self.births = 0
        self.deaths = 0
        self.deaths_by_reason: dict[str, int] = {}
        self.step_actions: dict[str, int] = {}
        self.probe_info_gain = 0.0
        self._memory_pool: list[float] = []
        self._registers = config.cell.internal_registers

        self.environment.initialize(self)
        if populate:
            self.seed_population()

    # -- geometry -------------------------------------------------------------

    def wrap(self, x: int, y: int) -> tuple[int, int]:
        """Normalise a coordinate. Returns ``(-1, -1)`` when off a bounded world."""
        if self.wrap_enabled:
            return x % self.width, y % self.height
        if 0 <= x < self.width and 0 <= y < self.height:
            return x, y
        return -1, -1

    def is_free(self, x: int, y: int) -> bool:
        if self.obstacle[y, x]:
            return False
        return not (self.config.physics.one_cell_per_tile and (x, y) in self.occupancy)

    def free_neighbour(self, x: int, y: int, rng) -> tuple[int, int] | None:
        offsets = list(_NEIGHBOURS_8)
        rng.shuffle(offsets)
        for dx, dy in offsets:
            nx, ny = self.wrap(x + dx, y + dy)
            if nx >= 0 and self.is_free(nx, ny):
                return nx, ny
        return None

    def variant_signature(self, variant: int) -> float:
        """Surface signature of a resource variant (section 16.7).

        Spread across the cue range so that a threshold tuned to one variant
        does not accidentally cover its neighbours.
        """
        variants = max(1, self.config.resources.variants)
        return 0.5 + 1.5 * (variant / max(1, variants - 1)) if variants > 1 else 1.0

    # -- population -----------------------------------------------------------

    def seed_population(self) -> None:
        cfg = self.config
        stream = self.rng.stream("seed")
        id_stream = self.rng.stream("ids")
        placed = 0
        attempts = 0
        limit = cfg.cell.start_population * 50

        while placed < cfg.cell.start_population and attempts < limit:
            attempts += 1
            x = stream.randrange(self.width)
            y = stream.randrange(self.height)
            if not self.is_free(x, y):
                continue
            genome = random_genome(
                stream,
                length=cfg.cell.genome_length,
                max_stage=cfg.cell.max_sensor_stage,
                registers=self._registers,
                channels=cfg.physics.signal_channels,
            )
            cell_id = new_cell_id(id_stream)
            cell = Cell(
                id=cell_id,
                lineage_id=cell_id,
                parent_id=None,
                generation=0,
                x=x,
                y=y,
                energy=cfg.cell.start_energy,
                age=0,
                integrity=cfg.physics.integrity_max,
                genome=genome,
                internal_state=[0.0] * self._registers,
                birth_step=0,
            )
            self.cells[cell_id] = cell
            self.occupancy[(x, y)] = cell_id
            self.lineage.register_founder(cell)
            self.ledger.initial_endowment += cell.energy
            self.next_cell_index += 1
            placed += 1

        self.refresh_memory_pool()
        self._emit(
            EventType.RUN_START,
            payload={
                "population": placed,
                "config_fingerprint": self.config.fingerprint(),
                "seed": self.config.world.seed,
                "controls": self.config.controls.active(),
            },
        )

    @property
    def population(self) -> int:
        return len(self.cells)

    def living_cells(self) -> list[Cell]:
        return [c for c in self.cells.values() if c.alive]

    def population_density(self) -> np.ndarray:
        density = np.zeros((self.height, self.width), dtype=np.float32)
        for x, y in self.occupancy:
            density[y, x] = 1.0
        return density

    # -- the loop -------------------------------------------------------------

    def step(self) -> None:
        """One timestep. Whitepaper section 7.1."""
        self.environment.update(self)
        self.step_actions = {}

        order = self.rng.shuffled(list(self.cells.keys()), "schedule")
        dead: list[str] = []

        for cell_id in order:
            cell = self.cells.get(cell_id)
            if cell is None or not cell.alive:
                continue

            obs = sense(cell, self)
            decision = decide(cell, obs, self)
            self.apply_cost(cell, decision)
            self.apply_action(cell, decision, obs)
            self.update_metabolism(cell)

            if self.should_reproduce(cell):
                self.spawn_child(cell)

            reason = self.should_die(cell)
            if reason is not None:
                self.kill(cell, reason)
                dead.append(cell_id)

        for cell_id in dead:
            self.cells.pop(cell_id, None)

        self.decay_signals()
        self.refresh_memory_pool()
        self.timestep += 1

        trace_interval = max(1, self.config.logging.trace_interval)
        if self.trace is not None and self.timestep % trace_interval == 0:
            self.trace.sample(self)

        if not self.cells and self.extinct_at is None:
            self.extinct_at = self.timestep
            self._emit(
                EventType.EXTINCTION,
                payload={"timestep": self.timestep, "births": self.births, "deaths": self.deaths},
            )

    # -- action pipeline ------------------------------------------------------

    def apply_cost(self, cell: Cell, decision: Decision) -> None:
        physics = self.config.physics
        ledger = self.ledger
        kind = decision.action.type

        if kind is ActionType.MOVE:
            cost, bucket = physics.move_cost, "spent_moving"
        elif kind is ActionType.STAY:
            cost, bucket = physics.idle_cost, "spent_idle"
        elif kind is ActionType.CONSUME:
            cost, bucket = physics.consume_action_cost, "spent_consuming"
        elif kind is ActionType.EMIT:
            cost, bucket = physics.signal_cost, "spent_signalling"
        elif kind is ActionType.WRITE_MEMORY:
            cost, bucket = physics.memory_cost, "spent_memory"
        elif kind is ActionType.DIVIDE:
            cost, bucket = physics.reproduction_cost, "spent_reproducing"
        elif kind is ActionType.PROBE:
            cost, bucket = physics.probe_cost, "spent_probing"
        elif kind is ActionType.ALTER_TILE:
            cost, bucket = physics.alter_tile_cost, "spent_altering"
        else:
            cost, bucket = 0.0, "spent_idle"

        if cost:
            cell.energy -= cost
            setattr(ledger, bucket, getattr(ledger, bucket) + cost)

        if decision.write is not None and physics.memory_cost:
            cell.energy -= physics.memory_cost
            ledger.spent_memory += physics.memory_cost

    def apply_action(self, cell: Cell, decision: Decision, obs: dict) -> None:
        """Whitepaper section 13.2."""
        action = decision.action
        cell.last_action = action
        self.step_actions[action.type.name] = self.step_actions.get(action.type.name, 0) + 1

        kind = action.type
        if kind is ActionType.MOVE and action.direction is not None:
            dx, dy = action.direction.delta
            nx, ny = self.wrap(cell.x + dx, cell.y + dy)
            if nx >= 0 and self.is_free(nx, ny):
                self.occupancy.pop((cell.x, cell.y), None)
                cell.x, cell.y = nx, ny
                self.occupancy[(nx, ny)] = cell.id

        elif kind is ActionType.CONSUME:
            gained = self.consume_resource(cell.x, cell.y, action.amount)
            if gained:
                self.add_energy(cell, gained)
                cell.energy_consumed += gained

        elif kind is ActionType.EMIT:
            self.emit_signal(cell, action.channel, action.value)

        elif kind is ActionType.WRITE_MEMORY:
            self.write_memory(cell, action.index, action.value)

        elif kind is ActionType.ALTER_TILE:
            self.alter_tile(cell, action.value)

        elif kind is ActionType.PROBE:
            self.probe(cell, action.index)

        if decision.write is not None:
            self.write_memory(cell, decision.write.index, decision.write.value)

        if self._should_log_action(cell):
            self._emit(
                EventType.ACTION,
                cell_id=cell.id,
                lineage_id=cell.lineage_id,
                position=(cell.x, cell.y),
                energy=cell.energy,
                payload={"action": action.to_dict(), "gene": decision.gene_index},
            )

    def update_metabolism(self, cell: Cell) -> None:
        physics = self.config.physics
        damage = float(self.hazard[cell.y, cell.x])
        if damage > 0.0:
            cell.integrity -= damage * 0.1
        elif cell.integrity < physics.integrity_max:
            cell.integrity = min(physics.integrity_max, cell.integrity + physics.integrity_regen)
        cell.age += 1

    # -- energy ---------------------------------------------------------------

    def add_energy(self, cell: Cell, amount: float) -> None:
        cap = self.config.physics.max_energy
        cell.energy += amount
        if cell.energy > cap:
            self.ledger.lost_to_cap += cell.energy - cap
            cell.energy = cap

    def consume_resource(self, x: int, y: int, max_amount: float) -> float:
        physics = self.config.physics
        available = float(self.resource[y, x])
        if available <= 0.0:
            return 0.0
        cap = max_amount if max_amount > 0 else physics.max_consume_per_step
        taken = min(available, cap)
        self.resource[y, x] = available - taken
        gained = taken * physics.consume_rate
        self.ledger.harvested += gained
        if self.config.logging.log_resource_changes:
            self._emit(
                EventType.RESOURCE_CHANGE,
                position=(x, y),
                payload={"before": round(available, 4), "after": round(available - taken, 4),
                         "cause": "CONSUME"},
            )
        return gained

    # -- memory, signals, markers, probes -------------------------------------

    def write_memory(self, cell: Cell, index: int, value: float) -> None:
        """The single mutation point for internal registers (invariant 4.3)."""
        if self.config.controls.disable_memory:
            return
        if 0 <= index < len(cell.internal_state):
            cell.internal_state[index] = max(-1e6, min(1e6, float(value)))

    def emit_signal(self, cell: Cell, channel: int, value: float) -> None:
        physics = self.config.physics
        if not (0 <= channel < physics.signal_channels):
            return
        self.signals.append(
            Signal(
                x=cell.x,
                y=cell.y,
                channel=channel,
                value=float(value),
                ttl=physics.signal_ttl,
                emitter_id=cell.id,
                emitted_at=self.timestep,
            )
        )
        cell.signals_emitted += 1
        if self.config.logging.log_signals:
            self._emit(
                EventType.SIGNAL_EMIT,
                cell_id=cell.id,
                lineage_id=cell.lineage_id,
                position=(cell.x, cell.y),
                payload={
                    "channel": channel,
                    "value": round(float(value), 4),
                    "resource_here": round(float(self.resource[cell.y, cell.x]), 4),
                    "hazard_here": round(float(self.hazard[cell.y, cell.x]), 4),
                },
            )

    def alter_tile(self, cell: Cell, value: float) -> None:
        """Persistent environmental modification: the substrate culture needs."""
        if self.config.controls.disable_markers:
            return
        self.marker[cell.y, cell.x] = min(5.0, self.marker[cell.y, cell.x] + float(value))

    def probe(self, cell: Cell, index: int) -> float:
        """Costly intervention that converts hidden state into stored information.

        Whitepaper section 14.7: the payoff is not immediate, it is that the
        cell's future actions can depend on something it could not otherwise see.
        """
        hidden = float(self.hidden_resource[cell.y, cell.x])
        cue = float(self.cue[cell.y, cell.x])
        revealed = hidden if hidden > 0.0 else cue
        self.write_memory(cell, index, revealed)
        cell.probes_performed += 1
        if revealed != 0.0:
            self.probe_info_gain += abs(revealed)
        return revealed

    def decay_signals(self) -> None:
        if not self.signals:
            if self.signal_field.any():
                self.signal_field.fill(0.0)
            return
        decay = self.config.physics.signal_decay
        survivors: list[Signal] = []
        for signal in self.signals:
            signal.ttl -= 1
            signal.value *= decay
            if signal.ttl > 0 and abs(signal.value) > 1e-4:
                survivors.append(signal)
        self.signals = survivors
        self.rebuild_signal_field()

    def rebuild_signal_field(self) -> None:
        self.signal_field.fill(0.0)
        for signal in self.signals:
            if 0 <= signal.channel < self.signal_field.shape[0]:
                self.signal_field[signal.channel, signal.y, signal.x] += signal.value

    def refresh_memory_pool(self) -> None:
        """Snapshot register values so the scrambled-memory control can preserve
        the marginal distribution while destroying the correspondence."""
        if not self.config.controls.scramble_memory:
            return
        pool: list[float] = []
        for cell in self.cells.values():
            pool.extend(cell.internal_state)
        self._memory_pool = pool or [0.0]

    def scrambled_memory_value(self, cell: Cell, index: int) -> float:
        if not self._memory_pool:
            return 0.0
        rng = self.rng.local("scramble-memory", self.timestep, cell.id, index)
        return float(self._memory_pool[rng.randrange(len(self._memory_pool))])

    def scrambled_signal_value(self, channel: int) -> float:
        rng = self.rng.local("scramble-signal", self.timestep, channel)
        if not self.signals:
            return 0.0
        signal = self.signals[rng.randrange(len(self.signals))]
        return float(signal.value) if signal.channel == channel else 0.0

    def record_catastrophe(self, phase: int, band: int) -> None:
        self.shocks.append(self.timestep)

    # -- lifecycle ------------------------------------------------------------

    def can_reproduce(self, cell: Cell) -> bool:
        physics = self.config.physics
        if self.config.controls.disable_reproduction:
            return False
        if cell.energy < physics.reproduction_threshold:
            return False
        if self.population >= self.config.stop.max_population:
            return False
        rng = self.rng.local("placement", self.timestep, cell.id)
        return self.free_neighbour(cell.x, cell.y, rng) is not None

    def should_reproduce(self, cell: Cell) -> bool:
        if not cell.alive:
            return False
        if self.config.physics.divide_mode == "action" and (
            cell.last_action is None or cell.last_action.type is not ActionType.DIVIDE
        ):
            return False
        return self.can_reproduce(cell)

    def spawn_child(self, parent: Cell) -> Cell | None:
        """Whitepaper section 7.2."""
        rng = self.rng.local("placement", self.timestep, parent.id)
        spot = self.free_neighbour(parent.x, parent.y, rng)
        if spot is None:
            return None

        cfg = self.config
        # Mutation draws from a stream keyed by the reproduction event, not by a
        # shared cursor, so sharding the population cannot change what evolves.
        mutation_rng = self.rng.local("mutation", self.timestep, parent.id, parent.offspring_count)
        result = mutate(
            parent.genome,
            mutation_rng,
            cfg.mutation,
            max_stage=cfg.cell.max_sensor_stage,
            registers=len(parent.internal_state),
            channels=cfg.physics.signal_channels,
        )

        id_stream = self.rng.stream("ids")
        fraction = cfg.physics.child_energy_fraction
        child_energy = parent.energy * fraction
        parent.energy = parent.energy * (1.0 - fraction)

        registers = max(result.registers, len(parent.internal_state))
        child = Cell(
            id=new_cell_id(id_stream),
            lineage_id=parent.lineage_id,
            parent_id=parent.id,
            generation=parent.generation + 1,
            x=spot[0],
            y=spot[1],
            energy=child_energy,
            age=0,
            integrity=cfg.physics.integrity_max,
            genome=result.genome,
            internal_state=[0.0] * registers,
            birth_step=self.timestep,
        )

        self.cells[child.id] = child
        self.occupancy[spot] = child.id
        self.lineage.register_birth(child, parent, self.timestep)
        parent.offspring_count += 1
        self.births += 1
        self.next_cell_index += 1

        if cfg.logging.log_births:
            self._emit(
                EventType.BIRTH,
                cell_id=child.id,
                parent_id=parent.id,
                lineage_id=child.lineage_id,
                position=spot,
                genome_hash=child.genome.hash,
                energy=child.energy,
                payload={"generation": child.generation},
            )
        if cfg.logging.log_mutations and result.records:
            self._emit(
                EventType.MUTATION,
                cell_id=child.id,
                parent_id=parent.id,
                lineage_id=child.lineage_id,
                genome_hash=child.genome.hash,
                payload={
                    "parent_genome_hash": parent.genome.hash,
                    "mutations": [
                        {"kind": r.kind, "gene": r.gene_index, "detail": r.detail}
                        for r in result.records
                    ],
                },
            )
        return child

    def should_die(self, cell: Cell) -> DeathReason | None:
        """Whitepaper section 7.3."""
        if cell.energy <= 0.0:
            return DeathReason.STARVATION
        if cell.integrity <= 0.0:
            return DeathReason.INTEGRITY
        if cell.age > self.config.physics.max_age:
            return DeathReason.OLD_AGE
        return None

    def kill(self, cell: Cell, reason: DeathReason) -> None:
        cell.alive = False
        cell.death_step = self.timestep
        cell.death_reason = reason
        # May be negative when the final action overdrew the account; that is
        # exactly the residual the conservation identity expects.
        self.ledger.lost_at_death += cell.energy
        self.occupancy.pop((cell.x, cell.y), None)
        self.lineage.register_death(cell, self.timestep)
        self.deaths += 1
        self.deaths_by_reason[reason.name] = self.deaths_by_reason.get(reason.name, 0) + 1
        if self.config.logging.log_deaths:
            self._emit(
                EventType.DEATH,
                cell_id=cell.id,
                lineage_id=cell.lineage_id,
                position=(cell.x, cell.y),
                genome_hash=cell.genome.hash,
                energy=cell.energy,
                payload={
                    "reason": reason.name,
                    "age": cell.age,
                    "generation": cell.generation,
                    "offspring": cell.offspring_count,
                },
            )

    # -- reporting ------------------------------------------------------------

    def living_energy(self) -> float:
        return float(sum(c.energy for c in self.cells.values()))

    def stats(self) -> dict[str, Any]:
        cells = list(self.cells.values())
        genome_hashes = {c.genome.hash for c in cells}
        return {
            "timestep": self.timestep,
            "population": len(cells),
            "births": self.births,
            "deaths": self.deaths,
            "deaths_by_reason": dict(self.deaths_by_reason),
            "mean_energy": round(self.living_energy() / len(cells), 4) if cells else 0.0,
            "total_resource": round(float(self.resource.sum()), 4),
            "total_hazard": round(float(self.hazard.sum()), 4),
            "total_marker": round(float(self.marker.sum()), 4),
            "active_signals": len(self.signals),
            "distinct_genomes": len(genome_hashes),
            "max_generation": self.lineage.max_generation(),
            "mean_genome_length": (
                round(sum(len(c.genome) for c in cells) / len(cells), 4) if cells else 0.0
            ),
            "energy_balance": round(self.ledger.balance(self.living_energy()), 6),
        }

    def _should_log_action(self, cell: Cell) -> bool:
        cfg = self.config.logging
        if not cfg.log_actions:
            return False
        rate = cfg.action_sample_rate
        if rate >= 1.0:
            return True
        if rate <= 0.0:
            return False
        return self.rng.local("action-sample", self.timestep, cell.id).random() < rate

    def _emit(self, event_type: EventType, **kwargs: Any) -> None:
        if self.event_log is not None:
            self.event_log.emit(event_type, self.timestep, **kwargs)


def new_world_id(seed: int) -> str:
    return str(uuid.UUID(int=seed % (1 << 128), version=4))
