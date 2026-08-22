"""Parallel execution must not change what evolves.

Section 11.2: "Parallel execution must not change biological outcomes." That
holds because a run is fully determined by its config and seed, and every
cell-level draw comes from a stream keyed on that cell's identity rather than a
shared cursor. These tests hold the guarantee in place, since a regression here
would be invisible -- results would simply differ from run to run.
"""

from __future__ import annotations

import os

import pytest

from worldzero.core.config import SimulationConfig
from worldzero.experiments.runner import ExperimentRunner, resolve_workers
from worldzero.experiments.suite import ExperimentSpec

SMALL = {
    "world": {"width": 20, "height": 20},
    "cell": {"start_population": 30},
    "resources": {"regime": "regenerating", "initial_density": 0.16, "regen_rate": 0.1},
    "hazards": {"regime": "none"},
    "logging": {"metrics_interval": 50, "trace_interval": 25, "checkpoint_interval": 0},
    "stop": {"max_steps": 150},
}


def _config() -> SimulationConfig:
    return SimulationConfig(name="par").merged(SMALL)


def test_resolve_workers_leaves_a_core_free() -> None:
    auto = resolve_workers(0)

    assert auto >= 1
    assert auto <= max(1, (os.cpu_count() or 2) - 1)
    assert resolve_workers(3) == 3
    assert resolve_workers(None) == auto


def test_parallel_batch_matches_sequential(tmp_path) -> None:
    seeds = [1, 2, 3, 4]

    sequential = ExperimentRunner(tmp_path / "seq", write_events=False, workers=1)
    parallel = ExperimentRunner(tmp_path / "par", write_events=False, workers=4)

    a = sequential.run_batch([_config()], seeds)
    b = parallel.run_batch([_config()], seeds)

    assert [r.seed for r in a] == [r.seed for r in b], "ordering must not depend on workers"
    assert [r.final_stats for r in a] == [r.final_stats for r in b]
    assert [r.fitness() for r in a] == [r.fitness() for r in b]


def test_parallel_experiment_matches_sequential(tmp_path) -> None:
    spec = ExperimentSpec(
        experiment_id="EP",
        name="parallel check",
        goal="",
        overrides=SMALL,
        controls=("random", "no_mutation"),
        detectors=("self_maintenance",),
    )
    seeds = [1, 2, 3]

    sequential = ExperimentRunner(tmp_path / "seq", write_events=False, workers=1)
    parallel = ExperimentRunner(tmp_path / "par", write_events=False, workers=4)

    a = sequential.run_experiment(spec, seeds)
    b = parallel.run_experiment(spec, seeds)

    assert [r.final_stats for r in a.treatment] == [r.final_stats for r in b.treatment]
    assert set(a.controls) == set(b.controls)
    for name, runs in a.controls.items():
        assert [r.seed for r in runs] == [r.seed for r in b.controls[name]]
        assert [r.final_stats for r in runs] == [r.final_stats for r in b.controls[name]]
    assert a.passed == b.passed
    assert a.ladder == b.ladder


@pytest.mark.parametrize("workers", [1, 4])
def test_controls_are_grouped_by_name(tmp_path, workers: int) -> None:
    """Flattening every arm into one pool must not scramble the grouping."""
    runner = ExperimentRunner(tmp_path / f"w{workers}", write_events=False, workers=workers)

    controls = runner.run_controls(_config(), ["random", "no_mutation"], [1, 2])

    assert sorted(controls) == ["no_mutation", "random"]
    for name, runs in controls.items():
        assert [r.seed for r in runs] == [1, 2]
        assert all(r.label == name for r in runs)
