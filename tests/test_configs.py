"""The shipped configs must load, and configs/ablations.yaml must not drift.

A stale ablation file is worse than none: section 17 results are only
interpretable if the documented override is the one the code actually applies.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from worldzero.core.config import SimulationConfig
from worldzero.core.world import World
from worldzero.experiments.controls import CONTROLS, apply_control
from worldzero.experiments.suite import SUITE

CONFIG_DIR = Path(__file__).resolve().parents[1] / "configs"


def test_world_zero_config_loads_and_runs() -> None:
    config = SimulationConfig.from_yaml(CONFIG_DIR / "world_zero.yaml")

    assert config.world.width == 128
    assert config.physics.reproduction_threshold == 80.0
    assert config.cell.max_sensor_stage == 0

    small = config.merged({"world": {"width": 16, "height": 16}, "cell": {"start_population": 10}})
    world = World(small)
    for _ in range(25):
        world.step()
    assert world.timestep == 25


def test_ablations_file_matches_the_code() -> None:
    data = yaml.safe_load((CONFIG_DIR / "ablations.yaml").read_text(encoding="utf-8"))

    assert set(data) == set(CONTROLS), "configs/ablations.yaml has drifted from CONTROLS"
    for name, entry in data.items():
        spec = CONTROLS[name]
        assert entry["purpose"] == spec.purpose
        assert entry["overrides"] == spec.overrides


@pytest.mark.parametrize("name", sorted(CONTROLS))
def test_every_control_produces_a_runnable_world(name: str, config: SimulationConfig) -> None:
    world = World(apply_control(config, name))
    for _ in range(20):
        world.step()
    assert world.timestep == 20


def test_unknown_control_is_rejected(config: SimulationConfig) -> None:
    with pytest.raises(ValueError, match="Unknown control"):
        apply_control(config, "no_such_control")


def test_unknown_config_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown config key"):
        SimulationConfig.from_dict({"world": {"not_a_real_key": 1}})


@pytest.mark.parametrize("experiment_id", sorted(SUITE))
def test_every_experiment_builds_a_runnable_config(experiment_id: str) -> None:
    spec = SUITE[experiment_id]
    config = spec.build_config(
        {"world": {"width": 16, "height": 16}, "cell": {"start_population": 10}}
    )

    world = World(config)
    for _ in range(20):
        world.step()

    assert world.timestep == 20
    assert all(name in CONTROLS for name in spec.controls)


def test_config_yaml_round_trips(config: SimulationConfig, tmp_path) -> None:
    path = tmp_path / "cfg.yaml"
    config.to_yaml(path)

    assert SimulationConfig.from_yaml(path).fingerprint() == config.fingerprint()


@pytest.mark.parametrize("experiment_id", sorted(SUITE))
def test_every_experiment_supports_a_living_population(experiment_id: str) -> None:
    """Guards the calibration in suite.py.

    At the published resource settings every experiment except E0 was extinct
    well before step 400, so its detectors compared dead worlds. Scaled down for
    speed; the densities are fractions of the grid, so they carry over.
    """
    spec = SUITE[experiment_id]
    config = spec.build_config(
        {"world": {"width": 40, "height": 40, "seed": 4}, "cell": {"start_population": 80}}
    )

    world = World(config)
    for _ in range(min(400, config.stop.max_steps)):
        world.step()
        if not world.cells:
            break

    assert world.cells, f"{experiment_id} went extinct at step {world.timestep}"
    assert world.lineage.max_generation() >= 3, f"{experiment_id} barely reproduced"
