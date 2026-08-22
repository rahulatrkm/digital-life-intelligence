"""Command line interface (whitepaper section 12, "How to run it").

Exposed as the ``worldzero`` console script. Every subcommand is a thin shell
over the library: the CLI resolves a :class:`SimulationConfig`, hands it to
:class:`ExperimentRunner`, and formats what comes back. No simulation logic
lives here, so a result obtained from the terminal and one obtained from a
notebook are the same computation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import yaml

from worldzero import __version__
from worldzero.core.config import SimulationConfig
from worldzero.core.world import World
from worldzero.detectors import build_ladder
from worldzero.experiments.controls import CONTROLS, apply_control, describe_controls
from worldzero.experiments.runner import ExperimentRunner
from worldzero.experiments.suite import SUITE, get_experiment
from worldzero.storage.checkpoints import load_checkpoint, save_checkpoint
from worldzero.storage.progress import (
    ProgressReporter,
    format_progress,
    read_progress,
    serve,
)
from worldzero.viz.render import plot_metrics, render_metrics, render_world, replay_summary

#: Series worth plotting by default: population and lifespan show whether the
#: world is alive, the genome/novelty columns show whether it is still changing.
DEFAULT_METRIC_KEYS: tuple[str, ...] = (
    "population",
    "mean_lifespan",
    "max_generation",
    "distinct_genomes",
    "mean_genome_length",
    "novelty_archive",
    "total_resource",
)


# -- config assembly ----------------------------------------------------------


def parse_override(item: str) -> dict[str, Any]:
    """Turn ``world.width=64`` into ``{"world": {"width": 64}}``.

    Values go through the YAML scalar parser so ``true``, ``0.05`` and ``hidden``
    arrive as bool, float and str rather than all as strings.
    """
    if "=" not in item:
        raise argparse.ArgumentTypeError(f"--set expects key.path=value, got '{item}'")
    path, raw = item.split("=", 1)
    keys = [k for k in path.strip().split(".") if k]
    if not keys:
        raise argparse.ArgumentTypeError(f"--set has an empty key path: '{item}'")

    value = yaml.safe_load(raw)
    nested: Any = value
    for key in reversed(keys):
        nested = {key: nested}
    return nested


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in overlay.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def collect_overrides(args: argparse.Namespace) -> dict[str, Any]:
    """Fold the convenience flags and every ``--set`` into one overlay."""
    overrides: dict[str, Any] = {}
    if getattr(args, "size", None):
        overrides["world"] = {"width": args.size, "height": args.size}
    if getattr(args, "steps", None):
        overrides["stop"] = {"max_steps": args.steps}
    if getattr(args, "population", None):
        overrides["cell"] = {"start_population": args.population}
    if getattr(args, "stage", None) is not None:
        overrides.setdefault("cell", {})["max_sensor_stage"] = args.stage
    if getattr(args, "accelerate", False):
        overrides["acceleration"] = {"enabled": True}
    for item in getattr(args, "set", None) or []:
        overrides = _deep_merge(overrides, parse_override(item))
    return overrides


def build_config(args: argparse.Namespace) -> SimulationConfig:
    """Resolve a config from ``--config``/``--experiment``, then apply overrides."""
    overrides = collect_overrides(args)

    if getattr(args, "experiment", None):
        config = get_experiment(args.experiment).build_config(overrides)
    else:
        config = (
            SimulationConfig.from_yaml(args.config)
            if getattr(args, "config", None)
            else SimulationConfig()
        )
        config = config.merged(overrides)

    if getattr(args, "seed", None) is not None:
        config = config.with_seed(args.seed)
    if getattr(args, "control", None):
        config = apply_control(config, args.control)
    return config


def seed_list(args: argparse.Namespace) -> list[int]:
    """Explicit ``--seeds 1 2 3`` wins; otherwise count consecutive from base."""
    if getattr(args, "seeds", None):
        return list(args.seeds)
    base = args.seed if getattr(args, "seed", None) is not None else 1
    return [base + i for i in range(max(1, getattr(args, "replicates", 1)))]


# -- commands -----------------------------------------------------------------


def _reporter(args: argparse.Namespace, command: str) -> ProgressReporter:
    """Progress lands in the output directory unless redirected."""
    path = getattr(args, "progress", None) or Path(args.output) / "progress.json"
    return ProgressReporter(path, command=command)


def cmd_run(args: argparse.Namespace) -> int:
    """One instrumented world: events, metrics, checkpoints, summary."""
    config = build_config(args)
    with _reporter(args, "run") as progress:
        progress.update(runs_total=1, experiment=config.name)
        runner = ExperimentRunner(
            args.output,
            write_events=not args.no_events,
            keep_traces=True,
            verbose=False,
            progress=progress,
        )
        print(
            f"world '{config.name}'  seed {config.world.seed}  "
            f"fingerprint {config.fingerprint()}"
        )
        print(f"  {config.world.width}x{config.world.height}  {config.stop.max_steps} steps  "
              f"resources={config.resources.regime}  hazards={config.hazards.regime}  "
              f"stage={config.cell.max_sensor_stage}")
        active = config.controls.active()
        if active:
            print(f"  controls: {', '.join(active)}")

        result = runner.run_world(config, label=args.label, seed=config.world.seed)

    print(f"\nfinished {result.steps} steps in {result.wallclock_seconds:.1f}s")
    if result.extinct_at is not None:
        print(f"  EXTINCT at step {result.extinct_at}")
    print(json.dumps(result.final_stats, indent=2, sort_keys=True))
    sparklines = render_metrics(result.metric_series, DEFAULT_METRIC_KEYS)
    if sparklines:
        print(f"\n{sparklines}")
    print(f"\noutputs: {Path(args.output) / result.run_id}")
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    """Live ASCII render, for eyeballing a world rather than measuring it."""
    config = build_config(args)
    world = World(config)
    every = max(1, args.every)

    try:
        for _ in range(config.stop.max_steps):
            world.step()
            if world.timestep % every == 0:
                # \033[H homes the cursor instead of scrolling, so successive
                # frames overdraw in place and read as animation.
                sys.stdout.write("\033[H\033[J" + render_world(world) + "\n")
                sys.stdout.flush()
            if not world.cells and config.stop.stop_on_extinction:
                print(f"\nextinct at step {world.timestep}")
                return 0
    except KeyboardInterrupt:
        print("\ninterrupted")
    print(f"\n{json.dumps(world.stats(), indent=2, sort_keys=True)}")
    return 0


def cmd_experiment(args: argparse.Namespace) -> int:
    """One staged experiment: treatment arm, its control arms, then detectors."""
    # run_experiment calls spec.build_config() itself, so CLI overrides have to
    # be folded into the spec rather than passed alongside it.
    spec = _spec_with_overrides(get_experiment(args.experiment_id), collect_overrides(args))
    with _reporter(args, f"experiment {spec.experiment_id}") as progress:
        runner = ExperimentRunner(
            args.output,
            write_events=not args.no_events,
            keep_traces=True,
            verbose=True,
            progress=progress,
            workers=args.workers,
        )
        report = runner.run_experiment(spec, seed_list(args))

    print(f"\nresult: {'PASS' if report.passed else 'FAIL'}")
    print(f"outputs: {Path(args.output) / f'{spec.experiment_id}-report'}")
    return 0 if report.passed else 1


def _spec_with_overrides(spec, overrides: dict[str, Any]):
    if not overrides:
        return spec
    from dataclasses import replace

    return replace(spec, overrides=_deep_merge(dict(spec.overrides), overrides))


def cmd_suite(args: argparse.Namespace) -> int:
    """Run E0-E9 in order and report the ladder they collectively reach."""
    ids = [e.upper() for e in args.only] if args.only else list(SUITE)
    unknown = [e for e in ids if e not in SUITE]
    if unknown:
        print(f"unknown experiments: {unknown}. Available: {sorted(SUITE)}", file=sys.stderr)
        return 2

    overrides = collect_overrides(args)
    seeds = seed_list(args)

    reports = []
    detections = []
    with _reporter(args, f"suite {','.join(ids)}") as progress:
        runner = ExperimentRunner(
            args.output,
            write_events=not args.no_events,
            keep_traces=True,
            verbose=True,
            progress=progress,
            workers=args.workers,
        )
        total = sum((1 + len(SUITE[e].controls)) * len(seeds) for e in ids)
        progress.update(runs_total=total)

        for index, experiment_id in enumerate(ids, start=1):
            spec = _spec_with_overrides(get_experiment(experiment_id), overrides)
            progress.update(
                force=True, phase=f"{experiment_id} ({index}/{len(ids)})", experiment=experiment_id
            )
            report = runner.run_experiment(spec, seeds)
            reports.append(report)
            detections.extend(report.detections)

    ladder = build_ladder(detections)
    print("\n" + "=" * 72)
    print("SUITE SUMMARY")
    print("=" * 72)
    for report in reports:
        print(f"  [{'PASS' if report.passed else 'fail'}] "
              f"{report.experiment_id} {report.name}")
    print(f"\nhighest contiguous stage: {ladder.highest_contiguous} "
          f"({ladder.to_dict()['highest_contiguous_name']})")
    print(f"highest stage reached at all: {ladder.highest_any}")

    Path(args.output).mkdir(parents=True, exist_ok=True)
    summary_path = Path(args.output) / "suite-summary.json"
    summary_path.write_text(
        json.dumps(
            {
                "version": __version__,
                "seeds": seeds,
                "experiments": [r.to_dict() for r in reports],
                "ladder": ladder.to_dict(),
            },
            indent=2,
            sort_keys=True,
        ),
        encoding="utf-8",
    )
    print(f"\nwrote {summary_path}")
    return 0 if all(r.passed for r in reports) else 1


def cmd_list(args: argparse.Namespace) -> int:
    print("experiments (whitepaper section 16)")
    for spec in SUITE.values():
        print(f"  {spec.experiment_id:<4} {spec.name}")
        print(f"       controls: {', '.join(spec.controls) or 'none'}")
        print(f"       detectors: {', '.join(spec.detectors) or 'none'}")
    print("\ncontrols (whitepaper section 17; every one removes a mechanism)")
    for control in describe_controls():
        print(f"  {control['name']:<20} {control['purpose']}")
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    config = build_config(args)
    if args.output_path:
        config.to_yaml(args.output_path)
        print(f"wrote {args.output_path}  (fingerprint {config.fingerprint()})")
    else:
        print(yaml.safe_dump(config.to_dict(), sort_keys=False))
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    if not Path(args.events).exists():
        print(f"no such event log: {args.events}", file=sys.stderr)
        return 2
    print(json.dumps(replay_summary(args.events, limit=args.limit), indent=2, sort_keys=True))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """Answer "is it running?" without attaching to the process."""
    path = Path(args.progress)
    if args.serve:
        serve(path, args.serve, host=args.host)
        return 0

    if not path.exists():
        print(f"no progress file: {path}", file=sys.stderr)
        return 2

    data = read_progress(path)
    print(json.dumps(data, indent=2, sort_keys=True) if args.json else format_progress(data))
    # Non-zero when the run is not alive, so a watchdog can act on the code.
    return 0 if data["alive"] else 1


def cmd_inspect(args: argparse.Namespace) -> int:
    """Summarise a checkpoint, loading it so a corrupt file fails here."""
    path = Path(args.checkpoint)
    if not path.exists():
        print(f"no such checkpoint: {path}", file=sys.stderr)
        return 2

    world = load_checkpoint(path)
    print(
        json.dumps(
            {
                "path": str(path),
                "size_bytes": path.stat().st_size,
                "run_id": world.run_id,
                "world_id": world.world_id,
                "code_version": __version__,
                "config_fingerprint": world.config.fingerprint(),
                "seed": world.config.world.seed,
                "controls": world.config.controls.active(),
                "stats": world.stats(),
                "lineage": world.lineage.summary(top=3),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    """Continue a saved world (whitepaper section 12.3: checkpoints are for replay)."""
    path = Path(args.checkpoint)
    if not path.exists():
        print(f"no such checkpoint: {path}", file=sys.stderr)
        return 2

    world = load_checkpoint(path)
    start = world.timestep
    print(f"resumed {world.run_id} at step {start}  pop {world.population}")

    for _ in range(args.steps):
        world.step()
        if not world.cells and world.config.stop.stop_on_extinction:
            print(f"extinct at step {world.timestep}")
            break

    print(f"ran {world.timestep - start} steps -> step {world.timestep}")
    print(json.dumps(world.stats(), indent=2, sort_keys=True))

    if args.save:
        saved = save_checkpoint(world, args.save)
        print(f"\nwrote {saved} ({saved.stat().st_size / 1024:.0f}K)")
    return 0


def cmd_plot(args: argparse.Namespace) -> int:
    path = Path(args.metrics)
    if not path.exists():
        print(f"no such metrics file: {path}", file=sys.stderr)
        return 2

    series = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if not series:
        print("metrics file is empty", file=sys.stderr)
        return 2

    keys = tuple(args.keys) if args.keys else DEFAULT_METRIC_KEYS
    print(render_metrics(series, keys))
    if args.png:
        if plot_metrics(series, keys, args.png):
            print(f"\nwrote {args.png}")
        else:
            print("\nmatplotlib not installed; install with: pip install worldzero[viz]")
    return 0


# -- argument parsing ---------------------------------------------------------


def _add_world_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--steps", type=int, help="override stop.max_steps")
    parser.add_argument("--size", type=int, help="square world edge length")
    parser.add_argument("--population", type=int, help="override cell.start_population")
    parser.add_argument("--stage", type=int, help="override cell.max_sensor_stage (0-3)")
    parser.add_argument("--accelerate", action="store_true", help="enable event-based skipping")
    parser.add_argument(
        "--set",
        action="append",
        metavar="KEY.PATH=VALUE",
        help="arbitrary config override, repeatable (e.g. --set resources.regime=hidden)",
    )


def _add_output_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-o", "--output", default="outputs", help="run output directory")
    parser.add_argument("--no-events", action="store_true", help="skip the JSONL event log")
    parser.add_argument(
        "--progress",
        help="progress file to write (default: <output>/progress.json)",
    )


def _add_worker_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--workers",
        type=int,
        default=0,
        help="parallel worlds; 0 auto-detects (runs are independent by design)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="worldzero",
        description="World Zero: a buildable digital-life simulator.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  worldzero run --steps 2000 --seed 7\n"
            "  worldzero watch --experiment E1 --every 20\n"
            "  worldzero experiment E2 --replicates 3\n"
            "  worldzero suite --only E0 E1 --steps 1500\n"
        ),
    )
    parser.add_argument("--version", action="version", version=f"worldzero {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run one instrumented world")
    run.add_argument("-c", "--config", help="YAML config file")
    run.add_argument("-e", "--experiment", help="start from a suite experiment config (E0-E9)")
    run.add_argument("--seed", type=int, help="world seed")
    run.add_argument("--label", default="treatment", help="label recorded on the run")
    run.add_argument("--control", choices=sorted(CONTROLS), help="apply an ablation control")
    _add_world_options(run)
    _add_output_options(run)
    run.set_defaults(func=cmd_run)

    watch = sub.add_parser("watch", help="live ASCII render of a world")
    watch.add_argument("-c", "--config", help="YAML config file")
    watch.add_argument("-e", "--experiment", help="start from a suite experiment config (E0-E9)")
    watch.add_argument("--seed", type=int, help="world seed")
    watch.add_argument("--control", choices=sorted(CONTROLS), help="apply an ablation control")
    watch.add_argument("--every", type=int, default=10, help="render every N steps")
    _add_world_options(watch)
    watch.set_defaults(func=cmd_watch)

    experiment = sub.add_parser("experiment", help="run one staged experiment with its controls")
    experiment.add_argument("experiment_id", help="experiment id, e.g. E2")
    experiment.add_argument("--seed", type=int, help="first seed")
    experiment.add_argument("--seeds", type=int, nargs="+", help="explicit seed list")
    experiment.add_argument(
        "--replicates",
        type=int,
        default=5,
        help="seeds per arm (below 5 the permutation test cannot reach p<0.05)",
    )
    _add_world_options(experiment)
    _add_output_options(experiment)
    _add_worker_options(experiment)
    experiment.set_defaults(func=cmd_experiment)

    suite = sub.add_parser("suite", help="run the full E0-E9 ladder")
    suite.add_argument("--only", nargs="+", help="subset of experiment ids")
    suite.add_argument("--seed", type=int, help="first seed")
    suite.add_argument("--seeds", type=int, nargs="+", help="explicit seed list")
    suite.add_argument(
        "--replicates",
        type=int,
        default=5,
        help="seeds per arm (below 5 the permutation test cannot reach p<0.05)",
    )
    _add_world_options(suite)
    _add_output_options(suite)
    _add_worker_options(suite)
    suite.set_defaults(func=cmd_suite)

    listing = sub.add_parser("list", help="list experiments and controls")
    listing.set_defaults(func=cmd_list)

    status = sub.add_parser("status", help="report whether a run is alive")
    status.add_argument(
        "progress",
        nargs="?",
        default="outputs/progress.json",
        help="path to a progress.json written by run/experiment/suite",
    )
    status.add_argument("--json", action="store_true", help="emit raw JSON")
    status.add_argument("--serve", type=int, metavar="PORT", help="serve status over HTTP")
    status.add_argument("--host", default="127.0.0.1", help="bind address for --serve")
    status.set_defaults(func=cmd_status)

    config = sub.add_parser("config", help="print or write a resolved config")
    config.add_argument("-c", "--config", help="YAML config file to start from")
    config.add_argument("-e", "--experiment", help="suite experiment to start from (E0-E9)")
    config.add_argument("--seed", type=int, help="world seed")
    config.add_argument("--control", choices=sorted(CONTROLS), help="apply an ablation control")
    config.add_argument("--output-path", help="write YAML here instead of stdout")
    _add_world_options(config)
    config.set_defaults(func=cmd_config)

    replay = sub.add_parser("replay", help="summarise an event log")
    replay.add_argument("events", help="path to events.jsonl or events.jsonl.gz")
    replay.add_argument("--limit", type=int, default=0, help="stop after N events")
    replay.set_defaults(func=cmd_replay)

    inspect = sub.add_parser("inspect", help="summarise a saved checkpoint")
    inspect.add_argument("checkpoint", help="path to a .json or .json.gz checkpoint")
    inspect.set_defaults(func=cmd_inspect)

    resume = sub.add_parser("resume", help="continue a saved checkpoint")
    resume.add_argument("checkpoint", help="path to a .json or .json.gz checkpoint")
    resume.add_argument("--steps", type=int, default=1000, help="steps to run")
    resume.add_argument("--save", help="write a new checkpoint here when finished")
    resume.set_defaults(func=cmd_resume)

    plot = sub.add_parser("plot", help="sparkline or PNG dashboard from a metrics file")
    plot.add_argument("metrics", help="path to metrics.jsonl")
    plot.add_argument("--keys", nargs="+", help="metric names to show")
    plot.add_argument("--png", help="also write a PNG dashboard here")
    plot.set_defaults(func=cmd_plot)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except (ValueError, argparse.ArgumentTypeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
