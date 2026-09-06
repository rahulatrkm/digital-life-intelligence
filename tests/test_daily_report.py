from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

from worldzero.storage.locking import exclusive_file_lock


@pytest.fixture
def daily():
    path = Path(__file__).resolve().parents[1] / "scripts" / "daily_report.py"
    spec = importlib.util.spec_from_file_location("daily_report", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_lock_prevents_overlap_and_releases_after_exit(tmp_path):
    path = tmp_path / "daily.lock"
    with exclusive_file_lock(path) as first:
        assert first
        with exclusive_file_lock(path) as second:
            assert not second
    with exclusive_file_lock(path) as third:
        assert third


def test_snapshot_updates_without_losing_notes_or_history(daily):
    original = (
        "# Status\n\n## Current state\n\nOld numbers\n\n### Notes\nKeep this\n\n"
        "<!-- daily-entries -->\n\n## 2026-08-31 IST\nOld entry\n"
    )
    first = daily.update_snapshot(original, "First snapshot")
    second = daily.update_snapshot(first, "New snapshot")
    assert "Old numbers" not in second
    assert "First snapshot" not in second
    assert "New snapshot" in second
    assert "Keep this" in second
    assert "Old entry" in second
    assert second.count(daily.SNAPSHOT_START) == 1


@pytest.mark.parametrize("state", ["failed", "running", "report-only"])
def test_incomplete_states_allow_retry(daily, state):
    text = f"## 2026-09-05 IST\n<!-- study-state: {state} -->\n**Fixed-cohort study.**\n"
    assert not daily.reported_successfully(text, "2026-09-05")


@pytest.mark.parametrize("state", ["complete", "batch-complete"])
def test_completed_states_block_duplicate(daily, state):
    text = f"## 2026-09-05 IST\n<!-- study-state: {state} -->\n**Fixed-cohort study.**\n"
    assert daily.reported_successfully(text, "2026-09-05")


def test_holm_adjustment_is_monotonic_and_preserves_input_order(daily):
    assert daily.holm_adjust([0.03, 0.01, 0.04]) == pytest.approx([0.06, 0.03, 0.06])
    assert daily.holm_adjust([0.8, 0.9]) == [1.0, 1.0]
    assert daily.holm_adjust([]) == []


def test_report_only_never_claims_a_new_run(daily, tmp_path, monkeypatch):
    status = tmp_path / "STATUS.md"
    status.write_text(
        "# Status\n\n## Current state\n\nOld\n\n### Notes\nKept\n\n<!-- daily-entries -->\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(daily, "STATUS", status)
    daily.write_report(
        "2026-09-05", daily.pooling.empty(), {}, "report-only", "No simulations run."
    )
    text = status.read_text(encoding="utf-8")
    assert "No simulations run." in text
    assert not daily.reported_successfully(text, "2026-09-05")
    assert "a full pooled ladder is not established" in text


def test_daily_entry_point_finishes_and_then_stops(daily, tmp_path, monkeypatch):
    from worldzero.experiments.suite import ExperimentSpec

    status = tmp_path / "STATUS.md"
    status.write_text(
        "# Status\n\n## Current state\nOld\n\n### Notes\nKeep\n\n<!-- daily-entries -->\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(daily, "STATUS", status)
    monkeypatch.setattr(daily, "OUTPUT", tmp_path / "runs")
    monkeypatch.setattr(daily, "SUMMARY", tmp_path / "runs" / "suite-summary.json")
    monkeypatch.setattr(daily, "POOL", tmp_path / "pool.json")
    monkeypatch.setattr(daily.pooling, "TARGET_SEEDS", 2)
    spec = ExperimentSpec(
        experiment_id="EX", name="daily", goal="", controls=("random",),
        detectors=("self_maintenance",), overrides={
            "world": {"width": 8, "height": 8}, "cell": {"start_population": 8},
            "stop": {"max_steps": 10}, "logging": {"checkpoint_interval": 0},
        },
    )
    monkeypatch.setattr(daily, "SUITE", {"EX": spec})
    args = SimpleNamespace(
        if_missing=False, no_commit=True, no_run=False, no_pool=False, prepare_only=False,
        finish=True, workers=1, replicates=2,
    )
    assert daily.run_daily(args) == 0
    assert daily.pooling.complete(daily.pooling.load(daily.POOL), ["EX"])
    assert "<!-- study-state: complete -->" in status.read_text(encoding="utf-8")
    monkeypatch.setattr(daily.study, "run_pending", lambda *args, **kwargs: pytest.fail("reran"))
    assert daily.run_daily(args) == 0


def test_pooled_report_does_not_depend_on_a_previous_suite_file(daily):
    pool = daily.pooling.empty()
    daily.pooling.merge_summary(pool, {"experiments": [{
        "experiment_id": "E4",
        "treatment": [{"seed": seed, "fitness": 1.0, "design_fingerprint": "treatment"}
                      for seed in range(6, 11)],
        "controls": {"scrambled_signals": [
            {"seed": seed, "fitness": 0.5, "design_fingerprint": "control"}
            for seed in range(6, 11)
        ]},
    }]})
    text = "\n".join(daily.pooled_lines(pool, {}))
    assert "E4" in text
    assert "provisional (5/30)" in text
    assert "settled null" not in text