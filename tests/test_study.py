from __future__ import annotations

import json

import pytest

from worldzero.experiments import pool as pooling
from worldzero.experiments import study
from worldzero.experiments.runner import ExperimentRunner
from worldzero.experiments.suite import ExperimentSpec


@pytest.fixture
def specs(monkeypatch):
    monkeypatch.setattr(pooling, "TARGET_SEEDS", 3)
    return {"EX": ExperimentSpec(
        experiment_id="EX", name="recovery", goal="", controls=("random",),
        detectors=("self_maintenance",), overrides={
            "name": "recover", "world": {"width": 8, "height": 8},
            "cell": {"start_population": 8},
            "stop": {"max_steps": 10},
            "logging": {"checkpoint_interval": 0, "trace_interval": 2, "metrics_interval": 5},
        },
    )}


def test_recovers_only_completed_matching_worlds(tmp_path, specs):
    runner = ExperimentRunner(tmp_path, write_events=False)
    config = specs["EX"].build_config()
    runner.run_experiment(specs["EX"], [6])
    runner.run_world(config, seed=7, steps=2)
    pool = pooling.empty()
    study.recover(pool, tmp_path, specs)
    assert pooling.analysis_seeds(pool, "EX") == [6]
    assert study.ensure_plan(pool, specs) == [6, 7, 8]
    assert len(study.pending_jobs(pool, specs)) == 4


def test_completion_saves_each_world_and_never_repeats_finished_work(tmp_path, specs, monkeypatch):
    pool = pooling.empty()
    path = tmp_path / "pool.json"
    study.ensure_plan(pool, specs)
    assert study.run_pending(pool, path, tmp_path, workers=1, specs=specs) == 6
    assert pooling.complete(pooling.load(path), ["EX"])
    monkeypatch.setattr(ExperimentRunner, "run_many", lambda *args, **kwargs: pytest.fail("reran"))
    assert study.run_pending(pool, path, tmp_path, workers=1, specs=specs) == 0


def test_partial_arm_is_not_recomputed(tmp_path, specs):
    runner = ExperimentRunner(tmp_path, write_events=False)
    runner.run_experiment(specs["EX"], [6])
    runner.run_world(specs["EX"].build_config(), seed=7)
    pool = pooling.empty()
    study.recover(pool, tmp_path, specs)
    jobs = study.pending_jobs(pool, specs, per_experiment=1)
    assert [(arm, seed) for _, _, arm, seed in jobs] == [("random", 7)]


def test_plan_is_persistent_not_reallocated_by_batch_size(specs):
    pool = pooling.empty()
    original = study.ensure_plan(pool, specs)
    study.pending_jobs(pool, specs, per_experiment=1)
    assert study.ensure_plan(pool, specs) == original
    assert len(study.pending_jobs(pool, specs, per_experiment=2)) == 4


def test_mismatched_provenance_is_not_recovered(tmp_path, specs):
    runner = ExperimentRunner(tmp_path, write_events=False)
    result = runner.run_world(specs["EX"].build_config(), seed=6)
    path = tmp_path / result.run_id / "summary.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["config_fingerprint"] = "wrong"
    path.write_text(json.dumps(data), encoding="utf-8")
    pool = pooling.empty()
    study.recover(pool, tmp_path, specs)
    assert pool["experiments"] == {}


def test_changed_simulation_cannot_mix_into_existing_study(specs, monkeypatch):
    pool = pooling.empty()
    study.ensure_plan(pool, specs)
    monkeypatch.setattr(study, "simulation_fingerprint", lambda: "changed")
    with pytest.raises(ValueError, match="Simulation code changed"):
        study.ensure_plan(pool, specs)


def test_scheduler_starts_longest_recorded_arm_first(specs):
    pool = pooling.empty()
    pool["cost_estimates"] = {"EX": {"treatment": 2.0, "random": 20.0}}
    jobs = study.pending_jobs(pool, specs)
    assert [arm for _, _, arm, _ in jobs[:3]] == ["random"] * 3


def test_predefined_comparisons_are_declared_controls():
    for experiment_id, control in study.FITNESS_CONTROLS.items():
        assert control in study.SUITE[experiment_id].controls