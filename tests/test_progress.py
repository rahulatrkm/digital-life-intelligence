"""Run progress and liveness reporting.

The motivating incident: a multi-hour calibration sweep died and left an empty
log and an untouched output directory, which is indistinguishable from a job
still working. Liveness has to be positively reported, and a stopped run has to
be detectable from the outside.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone

import pytest

from worldzero.cli import main
from worldzero.storage.progress import (
    STALE_AFTER_SECONDS,
    ProgressReporter,
    format_progress,
    read_progress,
)


def test_reporter_writes_a_file_immediately(tmp_path) -> None:
    path = tmp_path / "progress.json"
    ProgressReporter(path, command="run")

    assert path.exists()
    assert json.loads(path.read_text(encoding="utf-8"))["command"] == "run"


def test_context_manager_marks_running_then_finished(tmp_path) -> None:
    path = tmp_path / "progress.json"
    with ProgressReporter(path) as reporter:
        assert read_progress(path)["status"] == "running"
        assert read_progress(path)["alive"]
        reporter.update(step=10, force=True)

    assert read_progress(path)["status"] == "finished"
    assert not read_progress(path)["alive"]


def test_failure_is_recorded_not_swallowed(tmp_path) -> None:
    path = tmp_path / "progress.json"

    with pytest.raises(RuntimeError):  # noqa: SIM117 - the raise is the point
        with ProgressReporter(path):
            raise RuntimeError("world exploded")

    data = read_progress(path)
    assert data["status"] == "failed"
    assert "world exploded" in data["error"]
    assert not data["alive"]


def test_a_killed_run_reads_as_stale_not_running(tmp_path) -> None:
    """The incident: the process disappears without recording an outcome."""
    path = tmp_path / "progress.json"
    reporter = ProgressReporter(path)
    reporter.update(status="running", force=True)

    stale = datetime.now(timezone.utc) - timedelta(seconds=STALE_AFTER_SECONDS + 60)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["updated_utc"] = stale.isoformat()
    path.write_text(json.dumps(data), encoding="utf-8")

    result = read_progress(path)
    assert result["status"] == "stale"
    assert not result["alive"]
    assert "probably gone" in result["error"]


def test_throttling_does_not_hide_forced_updates(tmp_path) -> None:
    path = tmp_path / "progress.json"
    reporter = ProgressReporter(path, min_interval=1000.0)

    reporter.update(step=5)  # throttled away
    assert json.loads(path.read_text(encoding="utf-8"))["step"] == 0

    reporter.update(step=7, force=True)
    assert json.loads(path.read_text(encoding="utf-8"))["step"] == 7


def test_eta_appears_once_runs_complete(tmp_path) -> None:
    path = tmp_path / "progress.json"
    reporter = ProgressReporter(path)
    reporter.update(runs_total=4, force=True)

    assert read_progress(path)["eta_seconds"] is None

    reporter.run_finished()
    assert read_progress(path)["eta_seconds"] is not None


def test_no_path_is_a_silent_no_op() -> None:
    """The runner always holds a reporter; a disabled one must not break it."""
    reporter = ProgressReporter(None)
    reporter.update(step=3)
    reporter.run_finished()
    reporter.start_heartbeat()
    reporter.finish()


def test_heartbeat_refreshes_while_work_is_slow(tmp_path) -> None:
    """Liveness must not depend on work completing.

    A single world can run for minutes; a file refreshed only when a run
    finishes makes a healthy job cross the staleness threshold and read as dead.
    """
    path = tmp_path / "progress.json"
    with ProgressReporter(path, heartbeat=0.05) as reporter:
        first = read_progress(path)["updated_utc"]
        time.sleep(0.3)  # no work completes in this window
        second = read_progress(path)["updated_utc"]
        assert reporter.progress.runs_done == 0

    assert second > first, "heartbeat did not refresh the file"


def test_a_polling_reader_cannot_break_the_writer(tmp_path) -> None:
    """Windows refuses to replace a file another handle has open, so a status
    poller must not be able to crash the run it is watching."""
    path = tmp_path / "progress.json"
    with ProgressReporter(path, heartbeat=0.01) as reporter:
        for _ in range(60):
            read_progress(path)
            reporter.update(step=1, force=True)

    assert read_progress(path)["status"] == "finished"


def test_format_is_human_readable(tmp_path) -> None:
    path = tmp_path / "progress.json"
    reporter = ProgressReporter(path, command="suite")
    reporter.update(runs_total=10, step=50, max_steps=100, population=7, force=True)

    text = format_progress(read_progress(path))

    assert "status" in text
    assert "suite" in text
    assert "50/100" in text


def test_status_command_reports_and_sets_exit_code(tmp_path, capsys) -> None:
    path = tmp_path / "progress.json"

    with ProgressReporter(path, command="run"):
        assert main(["status", str(path)]) == 0  # alive
    capsys.readouterr()

    assert main(["status", str(path)]) == 1  # finished, so not alive
    assert "finished" in capsys.readouterr().out


def test_status_command_json_output(tmp_path, capsys) -> None:
    path = tmp_path / "progress.json"
    ProgressReporter(path, command="run").finish()

    main(["status", str(path), "--json"])

    assert json.loads(capsys.readouterr().out)["status"] == "finished"


def test_status_command_missing_file(tmp_path, capsys) -> None:
    assert main(["status", str(tmp_path / "nope.json")]) == 2
    assert "no progress file" in capsys.readouterr().err


def test_run_writes_progress_that_ends_finished(tmp_path) -> None:
    code = main(
        [
            "run",
            "--size", "16",
            "--population", "10",
            "--steps", "30",
            "--output", str(tmp_path),
            "--no-events",
        ]
    )

    assert code == 0
    data = read_progress(tmp_path / "progress.json")
    assert data["status"] == "finished"
    assert data["runs_done"] == 1
    assert data["command"] == "run"
