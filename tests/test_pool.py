"""Pooling must accumulate evidence without manufacturing it."""

from __future__ import annotations

import importlib.util
import json
from datetime import date
from pathlib import Path

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
                    {"seed": s, "fitness": treatment, "config_fingerprint": fingerprint}
                    for s in seeds
                ],
                "controls": {
                    "scrambled_signals": [
                        {"seed": s, "fitness": control, "config_fingerprint": "xyz"}
                        for s in seeds
                    ]
                },
            }
        ]
    }


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


def test_corrupt_pool_is_discarded_not_fatal(tmp_path):
    path = tmp_path / "pool.json"
    path.write_text("{not json", encoding="utf-8")
    assert pooling.load(path) == pooling.empty()


def test_version_change_discards_old_pool(tmp_path):
    path = tmp_path / "pool.json"
    path.write_text(json.dumps({"version": 0, "experiments": {"E4": {}}}), encoding="utf-8")
    assert pooling.load(path)["experiments"] == {}


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
