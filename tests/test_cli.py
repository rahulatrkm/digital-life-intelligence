"""CLI surface tests.

pyproject declares ``worldzero = worldzero.cli:main``; before this module
existed the entry point resolved to nothing, so an installed package failed at
first invocation. These tests keep that from regressing.
"""

from __future__ import annotations

import argparse
import json

import pytest

from worldzero.cli import build_parser, collect_overrides, main, parse_override


def test_entry_point_target_is_importable() -> None:
    from importlib.metadata import entry_points

    assert callable(main)
    scripts = {e.name: e.value for e in entry_points(group="console_scripts")}
    if "worldzero" in scripts:  # only present once the package is installed
        assert scripts["worldzero"] == "worldzero.cli:main"


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        ("world.width=64", {"world": {"width": 64}}),
        ("resources.regime=hidden", {"resources": {"regime": "hidden"}}),
        ("controls.random_actions=true", {"controls": {"random_actions": True}}),
        ("physics.move_cost=0.5", {"physics": {"move_cost": 0.5}}),
        ("name=demo", {"name": "demo"}),
    ],
)
def test_parse_override_types_values(item: str, expected: dict) -> None:
    assert parse_override(item) == expected


@pytest.mark.parametrize("bad", ["world.width", "=5", "  =1"])
def test_parse_override_rejects_malformed_input(bad: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError):
        parse_override(bad)


def test_overrides_merge_without_clobbering_siblings() -> None:
    args = build_parser().parse_args(
        ["run", "--size", "32", "--stage", "2", "--set", "cell.genome_length=4"]
    )
    overrides = collect_overrides(args)

    assert overrides["world"] == {"width": 32, "height": 32}
    assert overrides["cell"] == {"max_sensor_stage": 2, "genome_length": 4}


def test_list_command_runs(capsys) -> None:
    assert main(["list"]) == 0
    out = capsys.readouterr().out
    assert "E0" in out
    assert "scrambled_memory" in out


def test_config_command_emits_loadable_yaml(tmp_path, capsys) -> None:
    import yaml

    from worldzero.core.config import SimulationConfig

    assert main(["config", "--experiment", "E2", "--size", "24"]) == 0
    data = yaml.safe_load(capsys.readouterr().out)

    config = SimulationConfig.from_dict(data)
    assert config.world.width == 24
    assert config.cell.max_sensor_stage == 1


def test_config_command_writes_file(tmp_path) -> None:
    path = tmp_path / "out.yaml"
    assert main(["config", "--output-path", str(path)]) == 0
    assert path.exists()


def test_run_command_produces_outputs(tmp_path, capsys) -> None:
    code = main(
        [
            "run",
            "--size", "16",
            "--population", "10",
            "--steps", "40",
            "--seed", "3",
            "--output", str(tmp_path),
            "--set", "logging.metrics_interval=10",
        ]
    )
    assert code == 0

    run_dirs = [p for p in tmp_path.iterdir() if p.is_dir()]
    assert run_dirs, "run produced no output directory"

    summary = json.loads((run_dirs[0] / "summary.json").read_text(encoding="utf-8"))
    assert summary["steps"] == 40
    assert (run_dirs[0] / "events.jsonl").exists()
    assert (run_dirs[0] / "config.yaml").exists()


def test_run_command_accepts_a_control(tmp_path) -> None:
    code = main(
        [
            "run",
            "--size", "16",
            "--population", "10",
            "--steps", "20",
            "--control", "random",
            "--output", str(tmp_path),
            "--no-events",
        ]
    )
    assert code == 0


def test_replay_summarises_an_event_log(tmp_path, capsys) -> None:
    main(
        [
            "run",
            "--size", "16",
            "--population", "10",
            "--steps", "30",
            "--output", str(tmp_path),
        ]
    )
    capsys.readouterr()

    events = next(p / "events.jsonl" for p in tmp_path.iterdir() if p.is_dir())
    assert main(["replay", str(events)]) == 0

    report = json.loads(capsys.readouterr().out)
    assert report["events"] > 0
    assert "RUN_START" in report["counts"]


def test_plot_renders_sparklines(tmp_path, capsys) -> None:
    main(
        [
            "run",
            "--size", "16",
            "--population", "10",
            "--steps", "40",
            "--output", str(tmp_path),
            "--set", "logging.metrics_interval=10",
        ]
    )
    capsys.readouterr()

    metrics = next(p / "metrics" / "series.jsonl" for p in tmp_path.iterdir() if p.is_dir())
    assert main(["plot", str(metrics)]) == 0
    assert "population" in capsys.readouterr().out


def test_missing_files_exit_with_code_two(tmp_path, capsys) -> None:
    assert main(["replay", str(tmp_path / "nope.jsonl")]) == 2
    assert main(["plot", str(tmp_path / "nope.jsonl")]) == 2


def test_unknown_experiment_exits_with_code_two(capsys) -> None:
    assert main(["config", "--experiment", "E99"]) == 2
    assert "Unknown experiment" in capsys.readouterr().err
