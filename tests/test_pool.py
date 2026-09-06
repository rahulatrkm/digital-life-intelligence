"""Pooling must accumulate evidence without manufacturing it."""

from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from worldzero.experiments import pool as pooling

ROOT = Path(__file__).resolve().parents[1]


def _daily_report():
    spec = importlib.util.spec_from_file_location(
        "daily_report", ROOT / "scripts" / "daily_report.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def summary(seeds, fingerprint="abc", treatment=1.0, control=0.0):
    return {
        "experiments": [
            {
                "experiment_id": "E4",
                "required_detectors": ["communication"],
                "treatment": [
                    {"seed": s, "fitness": treatment, "design_fingerprint": fingerprint}
                    for s in seeds
                ],
                "controls": {
                    "scrambled_signals": [
                        {"seed": s, "fitness": control, "design_fingerprint": "xyz"}
                        for s in seeds
                    ]
                },
            }
        ]
    }


def test_design_fingerprint_ignores_the_seed():
    """Keying the pool on a seed-dependent hash resets it on every run."""
    from worldzero.core.config import SimulationConfig

    config = SimulationConfig()
    a, b = config.with_seed(1), config.with_seed(2)
    assert a.fingerprint() != b.fingerprint()
    assert a.design_fingerprint() == b.design_fingerprint()


def test_design_fingerprint_still_tracks_real_changes():
    from worldzero.core.config import SimulationConfig

    config = SimulationConfig()
    changed = config.merged({"world": {"width": config.world.width + 1}})
    assert config.design_fingerprint() != changed.design_fingerprint()


def test_pool_survives_a_seed_change():
    """Different seeds of one design must accumulate, not replace each other."""
    pool = pooling.empty()
    pooling.merge_summary(pool, summary([1, 2, 3], fingerprint="design-A"))
    pooling.merge_summary(pool, summary([4, 5, 6], fingerprint="design-A"))
    assert pooling.sample_size(pool, "E4") == 6


def test_merge_accumulates_across_runs():
    pool = pooling.empty()
    pooling.merge_summary(pool, summary([1, 2, 3]))
    pooling.merge_summary(pool, summary([4, 5, 6]))
    assert pooling.sample_size(pool, "E4") == 6


def test_rerunning_a_seed_does_not_inflate_the_sample():
    """The bug this module exists to prevent: repeats counted as replication."""
    pool = pooling.empty()
    pooling.merge_summary(pool, summary([1, 2, 3]))
    added = pooling.merge_summary(pool, summary([1, 2, 3]))
    assert pooling.sample_size(pool, "E4") == 3
    assert added["E4"] == 0


def test_config_change_starts_a_new_pool():
    pool = pooling.empty()
    pooling.merge_summary(pool, summary([1, 2, 3], fingerprint="abc"))
    pooling.merge_summary(pool, summary([4, 5, 6], fingerprint="different"))
    assert pooling.sample_size(pool, "E4") == 3


def test_pooled_test_uses_both_arms():
    pool = pooling.empty()
    pooling.merge_summary(pool, summary([1, 2, 3, 4, 5], treatment=1.0, control=0.0))
    result = pooling.pooled_test(pool, "E4", "scrambled_signals")
    assert result is not None
    assert result.n_treatment == 5
    assert result.statistic > 0


def test_pooled_test_missing_arm_is_none():
    pool = pooling.empty()
    pooling.merge_summary(pool, summary([1, 2, 3]))
    assert pooling.pooled_test(pool, "E4", "no_such_arm") is None


def test_provisional_until_target(tmp_path):
    pool = pooling.empty()
    pooling.merge_summary(pool, summary(range(1, pooling.TARGET_SEEDS)))
    assert pooling.provisional(pool, "E4")
    pooling.merge_summary(pool, summary([pooling.TARGET_SEEDS + 10]))
    assert not pooling.provisional(pool, "E4")


def test_round_trip(tmp_path):
    path = tmp_path / "pool.json"
    pool = pooling.empty()
    pooling.merge_summary(pool, summary([1, 2, 3]))
    pooling.save(path, pool)
    assert pooling.load(path) == pool


def test_corrupt_pool_is_not_silently_discarded(tmp_path):
    path = tmp_path / "pool.json"
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ValueError):
        pooling.load(path)
    assert path.read_text(encoding="utf-8") == "{not json"


def test_version_change_preserves_old_pool(tmp_path):
    path = tmp_path / "pool.json"
    path.write_text(json.dumps({"version": 0, "experiments": {"E4": {}}}), encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported"):
        pooling.load(path)


def test_fixed_cohort_does_not_keep_testing_new_seeds():
    pool = pooling.empty()
    pooling.merge_summary(pool, summary(range(10, 10 + pooling.TARGET_SEEDS)))
    initial = pooling.pooled_test(pool, "E4", "scrambled_signals").to_dict()
    pooling.merge_summary(pool, summary([1, 2, 100], treatment=100.0))
    assert pooling.analysis_seeds(pool, "E4") == list(range(10, 40))
    assert pooling.pooled_test(pool, "E4", "scrambled_signals").to_dict() == initial
    assert pooling.complete(pool, ["E4"])
    assert not pooling.complete(pool, ["E4", "E5"])


def test_pool_counts_only_seeds_present_in_every_arm():
    pool = pooling.empty()
    data = summary([1, 2, 3])
    data["experiments"][0]["controls"]["scrambled_signals"].pop()
    pooling.merge_summary(pool, data)
    assert pooling.sample_size(pool, "E4") == 2
    assert pooling.pooled_test(pool, "E4", "scrambled_signals").n_control == 2


def test_control_design_change_archives_both_arms():
    pool = pooling.empty()
    pooling.merge_summary(pool, summary([1, 2]))
    data = summary([3, 4])
    for run in data["experiments"][0]["controls"]["scrambled_signals"]:
        run["design_fingerprint"] = "changed-control"
    pooling.merge_summary(pool, data)
    assert pooling.analysis_seeds(pool, "E4") == [3, 4]
    assert set(pool["archives"]["E4"][0]["arms"]["treatment"]) == {"1", "2"}


def test_mixed_design_batch_is_rejected_without_mutating_pool():
    pool = pooling.empty()
    data = summary([1, 2])
    data["experiments"][0]["treatment"][1]["design_fingerprint"] = "other"
    with pytest.raises(ValueError, match="mixed design"):
        pooling.merge_summary(pool, data)
    assert pool == pooling.empty()


def test_conflicting_repeat_cannot_replace_observed_fitness():
    pool = pooling.empty()
    pooling.merge_summary(pool, summary([1, 2]))
    before = json.dumps(pool, sort_keys=True)
    with pytest.raises(ValueError, match="conflicting"):
        pooling.merge_summary(pool, summary([1, 2], treatment=2.0))
    assert json.dumps(pool, sort_keys=True) == before


def test_daily_seeds_never_repeat_across_days():
    """The defect that made five daily reports identical."""
    daily = _daily_report()
    replicates = 5
    start = date(2026, 8, 30).toordinal()
    seen: set[int] = set()
    for offset in range(40):
        base = daily.seed_base(date.fromordinal(start + offset), replicates)
        block = set(range(base, base + replicates))
        assert not (block & seen), f"day {offset} reuses seeds {sorted(block & seen)}"
        seen |= block


def test_daily_seeds_skip_the_seeds_already_spent():
    daily = _daily_report()
    base = daily.seed_base(date(2026, 8, 30), 5)
    assert base >= 6, "seeds 1-5 were already used before rotation existed"


def test_failed_entry_does_not_block_a_retry():
    """A crash at 07:00 must not suppress every retry for the rest of the day."""
    daily = _daily_report()
    failed = f"## 2026-08-30 IST\n\n{daily.FAILED_MARKER}\n\n```\nboom\n```\n\n---\n"
    assert not daily.reported_successfully(failed, "2026-08-30")


def test_successful_entry_blocks_a_retry():
    daily = _daily_report()
    good = "## 2026-08-30 IST\n\n**Automated suite run.** Seeds 6-10.\n\n---\n"
    assert daily.reported_successfully(good, "2026-08-30")


def test_missing_entry_does_not_block():
    daily = _daily_report()
    assert not daily.reported_successfully("## 2026-08-29 IST\n\nfine\n", "2026-08-30")


def test_failure_of_one_day_does_not_read_the_next_days_entry():
    daily = _daily_report()
    text = (
        f"## 2026-08-30 IST\n\n{daily.FAILED_MARKER}\n\n---\n"
        "## 2026-08-29 IST\n\n**Automated suite run.**\n\n---\n"
    )
    assert not daily.reported_successfully(text, "2026-08-30")
    assert daily.reported_successfully(text, "2026-08-29")


def test_failed_suite_cannot_reuse_an_old_summary(tmp_path, monkeypatch):
    daily = _daily_report()
    path = tmp_path / "suite-summary.json"
    path.write_text(json.dumps({"seeds": [6, 7]}), encoding="utf-8")
    monkeypatch.setattr(daily, "OUTPUT", tmp_path)
    monkeypatch.setattr(daily, "SUMMARY", path)
    monkeypatch.setattr(
        daily.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=1, stdout="", stderr="crashed"),
    )
    ok, note = daily.run_suite(2, 6)
    assert not ok
    assert "No fresh suite summary" in note
    assert json.loads(path.read_text(encoding="utf-8"))["seeds"] == [6, 7]


def test_fresh_suite_with_failed_detectors_is_a_completed_run(tmp_path, monkeypatch):
    daily = _daily_report()
    path = tmp_path / "suite-summary.json"
    monkeypatch.setattr(daily, "OUTPUT", tmp_path)
    monkeypatch.setattr(daily, "SUMMARY", path)

    def completed_suite(command, **kwargs):
        assert command[command.index("--seed") + 1] == "41"
        path.write_text(json.dumps({"seeds": [41, 42]}), encoding="utf-8")
        return SimpleNamespace(returncode=1, stdout="detectors not passed", stderr="")

    monkeypatch.setattr(daily.subprocess, "run", completed_suite)
    assert daily.run_suite(2, 41)[0]


def test_fresh_suite_rejects_wrong_seeds(tmp_path, monkeypatch):
    daily = _daily_report()
    path = tmp_path / "suite-summary.json"
    monkeypatch.setattr(daily, "OUTPUT", tmp_path)
    monkeypatch.setattr(daily, "SUMMARY", path)

    def wrong_suite(*args, **kwargs):
        path.write_text(json.dumps({"seeds": [1, 2]}), encoding="utf-8")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(daily.subprocess, "run", wrong_suite)
    ok, note = daily.run_suite(2, 41)
    assert not ok
    assert "seeds do not match" in note
