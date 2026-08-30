"""Run configuration.

Defaults are the World Zero values from whitepaper Appendix A. Configs are
plain dataclasses so that a run's full parameter set can be serialised into the
event log -- section 11.2 requires config, code version, seed and inputs to
reproduce an identical log.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, fields
from pathlib import Path
from typing import Any

import yaml


@dataclass
class WorldConfig:
    width: int = 128
    height: int = 128
    max_steps: int = 1_000_000
    seed: int = 42
    obstacle_density: float = 0.0
    wrap: bool = True
    """Toroidal by default: hard walls create artificial corners that cells
    exploit as hazard shelters, which reads as evolved strategy but is geometry."""


@dataclass
class PhysicsConfig:
    """Whitepaper section 5.3."""

    move_cost: float = 1.0
    idle_cost: float = 0.1
    sense_cost: float = 0.05
    signal_cost: float = 0.5
    memory_cost: float = 0.01
    probe_cost: float = 2.0
    alter_tile_cost: float = 3.0
    consume_action_cost: float = 0.1
    consume_rate: float = 10.0
    max_consume_per_step: float = 1.0
    reproduction_threshold: float = 80.0
    reproduction_cost: float = 1.0
    child_energy_fraction: float = 0.4
    divide_mode: str = "automatic"
    """``automatic`` follows the section 7.1 loop: any cell over threshold
    replicates. ``action`` requires the genome to express DIVIDE, which makes
    replication itself an evolvable decision but risks early extinction."""
    max_age: int = 1000
    max_energy: float = 200.0
    hazard_damage_rate: float = 2.0
    integrity_max: float = 1.0
    integrity_regen: float = 0.02
    one_cell_per_tile: bool = True
    signal_ttl: int = 20
    signal_decay: float = 0.9
    signal_channels: int = 2
    marker_decay: float = 0.999
    """Markers fade ~1000x slower than signals; culture needs a substrate that
    outlives the individual (section 8)."""


@dataclass
class ResourceConfig:
    """Whitepaper section 5.4."""

    regime: str = "regenerating"
    initial_density: float = 0.08
    regen_rate: float = 0.05
    """Appendix A suggests 0.01, which starves every seeded population before
    selection can act (the section 19 'all cells die quickly' failure). 0.05 is
    the lowest rate that sustained a population over 3000 steps in the sweep."""
    max_per_tile: float = 10.0
    patch_radius: int = 3
    cycle_period: int = 400
    front_speed: float = 0.05
    cue_lead_time: int = 12
    cue_strength: float = 1.0
    variants: int = 1
    """Functionally identical resources with different surface signatures, used
    by the abstraction experiment (section 16.7)."""
    scarcity_factor: float = 1.0


@dataclass
class HazardConfig:
    """Whitepaper section 5.5."""

    regime: str = "static"
    initial_density: float = 0.02
    damage_rate: float = 2.0
    diffusion_rate: float = 0.05
    decay_rate: float = 0.01
    cue_lead_time: int = 10
    predator_count: int = 4
    predator_radius: int = 2
    season_period: int = 2000
    season_severity: float = 0.5


@dataclass
class CellConfig:
    start_energy: float = 50.0
    start_population: int = 200
    internal_registers: int = 4
    genome_length: int = 16
    max_sensor_stage: int = 0
    """Gates which sensors mutation may reach, matching the staged rollout in
    section 6.2. Stage 0 alone gives a purely reactive organism with no memory,
    no signalling and no environment modification -- the section 3 default."""


@dataclass
class MutationConfig:
    """Whitepaper section 6.5."""

    enabled: bool = True
    point_rate: float = 0.02
    insertion_rate: float = 0.005
    deletion_rate: float = 0.005
    duplication_rate: float = 0.005
    priority_swap_rate: float = 0.005
    sensor_rate: float = 0.01
    action_rate: float = 0.01
    memory_expansion_rate: float = 0.0005
    min_genome_length: int = 1
    max_genome_length: int = 64
    max_registers: int = 8


@dataclass
class ControlConfig:
    """Whitepaper section 17. Every flag removes a mechanism; none add one."""

    random_actions: bool = False
    disable_mutation: bool = False
    disable_reproduction: bool = False
    disable_memory: bool = False
    scramble_memory: bool = False
    scramble_signals: bool = False
    isolate_cells: bool = False
    static_environment: bool = False
    disable_markers: bool = False
    disable_probe: bool = False

    def active(self) -> list[str]:
        return [f.name for f in fields(self) if getattr(self, f.name)]

    @property
    def is_treatment(self) -> bool:
        return not self.active()


@dataclass
class LoggingConfig:
    log_births: bool = True
    log_deaths: bool = True
    log_mutations: bool = False
    log_actions: bool = False
    action_sample_rate: float = 0.0
    """Logging every action in a 128x128 world produces gigabytes per million
    steps; sample instead of truncating so the log stays statistically usable."""
    log_signals: bool = True
    log_resource_changes: bool = False
    metrics_interval: int = 100
    trace_interval: int = 25
    checkpoint_interval: int = 10_000
    snapshot_interval: int = 0
    flush_interval: int = 2000


@dataclass
class AccelerationConfig:
    """Whitepaper section 10."""

    enabled: bool = False
    stability_window: int = 200
    stability_tolerance: float = 0.01
    max_skip: int = 100
    exact_validation_interval: int = 50_000


@dataclass
class StopConfig:
    max_steps: int = 100_000
    stop_on_extinction: bool = True
    max_population: int = 20_000
    max_wallclock_seconds: float = 0.0


@dataclass
class SimulationConfig:
    name: str = "world_zero"
    description: str = ""
    world: WorldConfig = field(default_factory=WorldConfig)
    physics: PhysicsConfig = field(default_factory=PhysicsConfig)
    resources: ResourceConfig = field(default_factory=ResourceConfig)
    hazards: HazardConfig = field(default_factory=HazardConfig)
    cell: CellConfig = field(default_factory=CellConfig)
    mutation: MutationConfig = field(default_factory=MutationConfig)
    controls: ControlConfig = field(default_factory=ControlConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    acceleration: AccelerationConfig = field(default_factory=AccelerationConfig)
    stop: StopConfig = field(default_factory=StopConfig)

    # -- serialisation --------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SimulationConfig:
        return _build(cls, data or {})

    @classmethod
    def from_yaml(cls, path: str | Path) -> SimulationConfig:
        with open(path, encoding="utf-8") as handle:
            return cls.from_dict(yaml.safe_load(handle) or {})

    def to_yaml(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            yaml.safe_dump(self.to_dict(), handle, sort_keys=False)

    def merged(self, overrides: dict[str, Any]) -> SimulationConfig:
        """Return a copy with a nested-dict overlay applied."""
        return SimulationConfig.from_dict(_deep_merge(self.to_dict(), overrides))

    def with_seed(self, seed: int) -> SimulationConfig:
        return self.merged({"world": {"seed": int(seed)}})

    def fingerprint(self) -> str:
        """Stable hash of the whole config, stored with every run."""
        import hashlib
        import json

        blob = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]

    def design_fingerprint(self) -> str:
        """Hash of the world design, ignoring the seed.

        ``fingerprint`` covers the seed, so it differs for every run and cannot
        identify "the same experiment at another seed". Anything pooling runs
        across seeds needs this instead, or it sees each run as a new design.
        """
        import hashlib
        import json

        data = self.to_dict()
        data.get("world", {}).pop("seed", None)
        blob = json.dumps(data, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _build(cls: type, data: dict[str, Any]) -> Any:
    # `from __future__ import annotations` turns field types into strings, so
    # nested dataclasses are resolved through the explicit _NESTED table.
    kwargs: dict[str, Any] = {}
    known = {f.name for f in fields(cls)}
    for key, value in data.items():
        if key not in known:
            raise ValueError(f"Unknown config key '{key}' for {cls.__name__}")
        if isinstance(value, dict) and key in _NESTED:
            kwargs[key] = _build(_NESTED[key], value)
        else:
            kwargs[key] = value
    return cls(**kwargs)


_NESTED: dict[str, type] = {
    "world": WorldConfig,
    "physics": PhysicsConfig,
    "resources": ResourceConfig,
    "hazards": HazardConfig,
    "cell": CellConfig,
    "mutation": MutationConfig,
    "controls": ControlConfig,
    "logging": LoggingConfig,
    "acceleration": AccelerationConfig,
    "stop": StopConfig,
}


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out
