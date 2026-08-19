"""Staged experiments E0-E9 (whitepaper section 16).

Each experiment turns one capability pressure on and pairs it with the controls
that could explain the result away. The staging is not cosmetic: sensors and
actions are gated by ``cell.max_sensor_stage``, so a cell in E1 physically
cannot signal and a cell in E2 physically cannot emit or mark. This is what
stops a later mechanism from quietly carrying an earlier result.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from worldzero.core.config import SimulationConfig

#: Small enough that the whole suite runs on a laptop, large enough that a
#: population has room to differentiate. Override with --steps / --size.
BASE_OVERRIDES: dict[str, Any] = {
    "world": {"width": 64, "height": 64},
    "cell": {"start_population": 200, "max_sensor_stage": 0},
    "stop": {"max_steps": 4000},
    "logging": {"metrics_interval": 100, "trace_interval": 20, "checkpoint_interval": 0},
}


@dataclass(frozen=True)
class ExperimentSpec:
    experiment_id: str
    name: str
    goal: str
    overrides: dict[str, Any] = field(default_factory=dict)
    controls: tuple[str, ...] = ()
    detectors: tuple[str, ...] = ()

    def build_config(self, extra: dict[str, Any] | None = None) -> SimulationConfig:
        config = SimulationConfig(name=self.experiment_id.lower())
        config = config.merged(BASE_OVERRIDES)
        config = config.merged(self.overrides)
        if extra:
            config = config.merged(extra)
        return config


E0 = ExperimentSpec(
    experiment_id="E0",
    name="Viability",
    goal=(
        "Show that digital cells can persist and reproduce in a simple world, "
        "outliving a random-action baseline without exploding."
    ),
    overrides={
        "resources": {"regime": "regenerating"},
        "hazards": {"regime": "none"},
    },
    controls=("random", "no_reproduction"),
    detectors=("self_maintenance",),
)

E1 = ExperimentSpec(
    experiment_id="E1",
    name="Resource seeking",
    goal=(
        "Determine whether selection produces non-random movement toward "
        "resources, against random-action and no-mutation controls."
    ),
    overrides={
        "resources": {"regime": "static", "initial_density": 0.06},
        "hazards": {"regime": "static"},
    },
    controls=("random", "no_mutation"),
    detectors=("resource_behaviour",),
)

E2 = ExperimentSpec(
    experiment_id="E2",
    name="Memory pressure",
    goal=(
        "Introduce regenerating resources and delayed hazards where past "
        "observations matter; scramble memory in controls."
    ),
    overrides={
        "cell": {"max_sensor_stage": 1},
        "resources": {"regime": "regenerating", "regen_rate": 0.03},
        "hazards": {"regime": "delayed", "cue_lead_time": 10},
    },
    controls=("scrambled_memory", "no_memory", "random"),
    detectors=("memory",),
)

E3 = ExperimentSpec(
    experiment_id="E3",
    name="Prediction pressure",
    goal=(
        "Add cues that precede resources and hazards, and test whether lineages "
        "act before the future state is directly observable."
    ),
    overrides={
        "cell": {"max_sensor_stage": 1},
        "resources": {"regime": "hidden", "cue_lead_time": 12},
        "hazards": {"regime": "delayed", "cue_lead_time": 10},
    },
    controls=("no_memory", "random", "static_env"),
    detectors=("prediction",),
)

E4 = ExperimentSpec(
    experiment_id="E4",
    name="Communication pressure",
    goal=(
        "Create local information asymmetry where one cell can know something "
        "useful to another, and test whether signal channels become informative."
    ),
    overrides={
        "cell": {"max_sensor_stage": 3},
        "resources": {"regime": "hidden", "cue_lead_time": 12, "initial_density": 0.05},
        "hazards": {"regime": "spreading"},
        "physics": {"signal_channels": 2},
    },
    controls=("scrambled_signals", "isolated", "random"),
    detectors=("communication",),
)

E5 = ExperimentSpec(
    experiment_id="E5",
    name="Cooperation pressure",
    goal=(
        "Create conditions where groups outperform individuals: scarce "
        "resources and moving predator-like hazards."
    ),
    overrides={
        "cell": {"max_sensor_stage": 3},
        "resources": {"regime": "scarce", "scarcity_factor": 0.5, "regen_rate": 0.04},
        "hazards": {"regime": "predator", "predator_count": 6},
    },
    controls=("isolated", "random"),
    detectors=("cooperation",),
)

E6 = ExperimentSpec(
    experiment_id="E6",
    name="Abstraction pressure",
    goal=(
        "Vary surface details while preserving functional category, and test "
        "whether cells generalise from Food A/B/C to resource-like behaviour."
    ),
    overrides={
        "cell": {"max_sensor_stage": 2},
        "resources": {"regime": "regenerating", "variants": 4},
        "hazards": {"regime": "static"},
    },
    controls=("single_variant", "random"),
    detectors=("abstraction",),
)

E7 = ExperimentSpec(
    experiment_id="E7",
    name="Culture pressure",
    goal=(
        "Allow persistent environmental markers and test whether information "
        "survives the death of the cell that created it."
    ),
    overrides={
        "cell": {"max_sensor_stage": 2},
        "resources": {"regime": "cyclic", "cycle_period": 300},
        "hazards": {"regime": "seasonal", "season_period": 800},
        "physics": {"marker_decay": 0.999, "alter_tile_cost": 2.0},
    },
    controls=("no_markers", "random"),
    detectors=("culture",),
)

E8 = ExperimentSpec(
    experiment_id="E8",
    name="Scientific behaviour pressure",
    goal=(
        "Add costly probes whose payoff is delayed through improved prediction, "
        "and test whether organisms evolve experiment-like actions."
    ),
    overrides={
        "cell": {"max_sensor_stage": 2},
        "resources": {"regime": "hidden", "cue_lead_time": 15},
        "hazards": {"regime": "delayed"},
        "physics": {"probe_cost": 1.5},
    },
    controls=("no_probe", "random"),
    detectors=("scientific_behaviour",),
)

E9 = ExperimentSpec(
    experiment_id="E9",
    name="Intelligence acceleration",
    goal=(
        "Measure whether culture, external memory and experimentation increase "
        "the rate of future capability growth."
    ),
    overrides={
        "cell": {"max_sensor_stage": 3},
        "resources": {"regime": "cyclic", "cycle_period": 400, "variants": 3},
        "hazards": {"regime": "seasonal", "season_period": 1000},
        "stop": {"max_steps": 12000},
    },
    controls=("no_markers", "no_probe", "random"),
    detectors=("civilization", "intelligence_acceleration"),
)

SUITE: dict[str, ExperimentSpec] = {
    spec.experiment_id: spec for spec in (E0, E1, E2, E3, E4, E5, E6, E7, E8, E9)
}


def get_experiment(experiment_id: str) -> ExperimentSpec:
    spec = SUITE.get(experiment_id.upper())
    if spec is None:
        raise ValueError(f"Unknown experiment '{experiment_id}'. Available: {sorted(SUITE)}")
    return spec
