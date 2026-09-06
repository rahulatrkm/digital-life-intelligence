from __future__ import annotations

import numpy as np
import pytest

from worldzero.core.config import SimulationConfig
from worldzero.detectors import run_all_detectors
from worldzero.experiments.runner import ExperimentRunner
from worldzero.experiments.suite import ExperimentSpec
from worldzero.storage import result_cache


def small_config():
    return SimulationConfig(name="cached").merged({
        "world": {"width": 10, "height": 10},
        "cell": {"start_population": 12},
        "logging": {"metrics_interval": 5, "trace_interval": 2, "checkpoint_interval": 0},
        "stop": {"max_steps": 15},
    })


def test_cache_preserves_every_detector_input(tmp_path, monkeypatch):
    runner = ExperimentRunner(tmp_path, write_events=False, reuse_completed=True)
    original = runner.run_world(small_config(), seed=7)
    monkeypatch.setattr("worldzero.experiments.runner.World", lambda *args, **kwargs: pytest.fail(
        "a completed world was simulated again"
    ))
    restored = runner.run_world(small_config(), seed=7)
    assert restored.to_dict() == original.to_dict()
    assert restored.metric_series == original.metric_series
    assert restored.trace.samples == original.trace.samples
    assert restored.trace.tile_future == original.trace.tile_future
    assert restored.trace.signal_observations == original.trace.signal_observations
    for actual, expected in zip(
        restored.trace.future_resource(3), original.trace.future_resource(3), strict=True
    ):
        np.testing.assert_array_equal(actual, expected)
    assert [item.to_dict() for item in run_all_detectors([restored], {})] == [
        item.to_dict() for item in run_all_detectors([original], {})
    ]


def test_cache_identity_tracks_inputs_and_engine(tmp_path, monkeypatch):
    config = small_config()
    def path(**overrides):
        args = dict(output=tmp_path, config=config, label="treatment", steps=15,
                    keep_traces=True, write_events=False)
        return result_cache.cache_path(**(args | overrides))
    baseline = path()
    assert path(config=config.with_seed(999)) != baseline
    assert path(steps=30) != baseline
    assert path(keep_traces=False) != baseline
    assert path(write_events=True) != baseline
    monkeypatch.setattr(result_cache, "engine_fingerprint", lambda: "changed-engine")
    assert path() != baseline


def test_corrupt_cache_is_a_miss(tmp_path):
    path = tmp_path / "bad.json.gz"
    path.write_bytes(b"not a gzip file")
    assert result_cache.load_result(path, small_config()) is None


def test_parallel_retry_reuses_all_arms_and_keeps_verdict(tmp_path):
    config = small_config()
    spec = ExperimentSpec(
        experiment_id="EC", name="cache", goal="", overrides=config.to_dict(),
        controls=("random",), detectors=("self_maintenance",),
    )
    runner = ExperimentRunner(tmp_path, write_events=False, workers=2, reuse_completed=True)
    first = runner.run_experiment(spec, [1, 2])
    files = {path: path.stat().st_mtime_ns for path in tmp_path.glob(".result-cache/*.gz")}
    second = runner.run_experiment(spec, [1, 2])
    assert first.to_dict() == second.to_dict()
    assert {path: path.stat().st_mtime_ns for path in files} == files


@pytest.mark.parametrize("workers", [1, 2])
def test_streamed_results_are_delivered_without_retaining_traces(tmp_path, workers):
    runner = ExperimentRunner(tmp_path, write_events=False, workers=workers, reuse_completed=True)
    observed = []
    results = runner.run_many(
        [(small_config(), "treatment", seed) for seed in [1, 2]],
        on_result=lambda result: observed.append(result.seed), retain_results=False,
    )
    assert results == []
    assert sorted(observed) == [1, 2]
    assert len(list(tmp_path.glob(".result-cache/*.gz"))) == 2