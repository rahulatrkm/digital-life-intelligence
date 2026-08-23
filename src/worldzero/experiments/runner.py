"""Experiment runner (whitepaper sections 13.3 and 16).

    for config in experiment_configs:
      for seed in seeds:
        run_id = create_run(config, seed)
        world = initialize_world(config, seed)
        while not stop_condition(world):
            step(world)
            if metric_due(world): compute_metrics(world)
            if detector_due(world): run_detectors(world)
        persist_summary(run_id, world)

Detectors run once at the end rather than per-step, because every one of them
compares a treatment arm against control arms and neither arm exists until its
runs have finished.
"""

from __future__ import annotations

import os
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from worldzero.core.acceleration import Accelerator
from worldzero.core.config import SimulationConfig
from worldzero.core.world import World
from worldzero.detectors import DetectionResult, build_ladder, run_all_detectors
from worldzero.experiments.controls import CONTROLS, apply_control
from worldzero.metrics.core import MetricEngine
from worldzero.metrics.traces import BehaviorTrace
from worldzero.results import RunResult
from worldzero.storage.checkpoints import save_checkpoint
from worldzero.storage.events import EventLog, EventType
from worldzero.storage.progress import ProgressReporter
from worldzero.storage.run_dir import RunDirectory


@dataclass
class ExperimentReport:
    experiment_id: str
    name: str
    goal: str
    treatment: list[RunResult] = field(default_factory=list)
    controls: dict[str, list[RunResult]] = field(default_factory=dict)
    detections: list[DetectionResult] = field(default_factory=list)
    ladder: dict[str, Any] = field(default_factory=dict)
    required: tuple[str, ...] = ()
    """Detectors the spec declares. Stages 0-1 are always *measured* so the
    ladder has a base, but an experiment is not judged on a capability it was
    never designed to elicit -- E0 tests viability, not resource seeking."""

    @property
    def passed(self) -> bool:
        """An experiment passes when every detector it was set up to test fired."""
        relevant = [
            d
            for d in self.detections
            if d.criteria and (not self.required or d.name in self.required)
        ]
        return bool(relevant) and all(d.detected for d in relevant)

    def to_dict(self) -> dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "name": self.name,
            "goal": self.goal,
            "passed": self.passed,
            "required_detectors": list(self.required),
            "treatment": [r.to_dict() for r in self.treatment],
            "controls": {k: [r.to_dict() for r in v] for k, v in self.controls.items()},
            "detections": [d.to_dict() for d in self.detections],
            "ladder": self.ladder,
        }

    def summary_lines(self) -> list[str]:
        lines = [f"{self.experiment_id}  {self.name}", f"  goal: {self.goal}"]
        for detection in self.detections:
            required = not self.required or detection.name in self.required
            if detection.detected:
                mark = "PASS"
            elif required:
                mark = "fail"
            else:
                mark = "n/a "
            lines.append(
                f"  [{mark}] stage {detection.stage:>2} {detection.name} "
                f"(confidence {detection.confidence:.2f})"
            )
            for criterion in detection.criteria:
                if not criterion.passed:
                    lines.append(f"           - {criterion.name}: {criterion.detail}")
        if self.ladder:
            lines.append(
                f"  ladder: highest contiguous stage "
                f"{self.ladder.get('highest_contiguous_stage')} "
                f"({self.ladder.get('highest_contiguous_name')})"
            )
        return lines


def resolve_workers(requested: int | None) -> int:
    """0 or None means "use the machine", leaving one core for everything else.

    The cap is the logical processor count rather than the physical core count:
    the step loop is pure Python and spends much of its time on dict and
    attribute lookups rather than saturating an execution port, so the extra SMT
    threads do carry useful work. Measured with scripts/benchmark_workers.py.
    """
    if requested and requested > 0:
        return requested
    return max(1, (os.cpu_count() or 2) - 1)


def _run_world_task(payload: tuple[Any, ...]) -> RunResult:
    """Worker entry point. Must be module level so it can be pickled.

    Section 11.2 requires that parallel execution not change biological
    outcomes, which holds here because a run is fully determined by its config
    and seed: every cell-level draw comes from a stream keyed on that cell's
    identity rather than a shared cursor, so nothing depends on scheduling.
    """
    output_dir, config, label, seed, steps, write_events, keep_traces = payload
    runner = ExperimentRunner(
        output_dir,
        write_events=write_events,
        keep_traces=keep_traces,
        verbose=False,
    )
    return runner.run_world(config, label=label, seed=seed, steps=steps)


class ExperimentRunner:
    """Runs single worlds, control sets and whole experiments."""

    def __init__(
        self,
        output_dir: str | Path = "outputs",
        *,
        write_events: bool = True,
        keep_traces: bool = True,
        verbose: bool = False,
        progress: ProgressReporter | None = None,
        workers: int | None = 1,
    ) -> None:
        self.output_dir = Path(output_dir)
        self.write_events = write_events
        self.keep_traces = keep_traces
        self.verbose = verbose
        # A no-op reporter keeps the call sites free of None checks.
        self.progress = progress or ProgressReporter(None)
        self.workers = resolve_workers(workers)

    # -- one world ------------------------------------------------------------

    def run_world(
        self,
        config: SimulationConfig,
        *,
        label: str = "treatment",
        seed: int | None = None,
        steps: int | None = None,
    ) -> RunResult:
        if seed is not None:
            config = config.with_seed(seed)
        seed = config.world.seed
        steps = steps or config.stop.max_steps

        run_id = f"{config.name}-{label}-s{seed}"
        run_dir = RunDirectory.create(self.output_dir, run_id)
        run_dir.write_provenance(config, seed)
        config.to_yaml(run_dir.config_path)

        self.progress.update(
            force=True,
            phase=f"{config.name}/{label}",
            label=label,
            seed=seed,
            step=0,
            max_steps=steps,
            population=0,
        )

        event_log = None
        if self.write_events:
            event_log = EventLog(
                run_dir.events_path,
                run_id=run_id,
                world_id=f"world-{seed}",
                flush_interval=config.logging.flush_interval,
            )

        trace = BehaviorTrace() if self.keep_traces else None
        metrics = MetricEngine()
        accelerator = Accelerator(config.acceleration)

        started = time.perf_counter()
        world = World(
            config,
            run_id=run_id,
            world_id=f"world-{seed}",
            event_log=event_log,
            trace=trace,
        )

        try:
            while not self._should_stop(world, steps, started):
                accelerator.observe(world)
                if not accelerator.maybe_skip(world):
                    world.step()

                if world.timestep % max(1, config.logging.metrics_interval) == 0:
                    metrics.compute(world, trace)
                    self.progress.update(step=world.timestep, population=world.population)
                if (
                    config.logging.checkpoint_interval
                    and world.timestep % config.logging.checkpoint_interval == 0
                ):
                    path = save_checkpoint(world, run_dir.checkpoint_path(world.timestep))
                    if event_log is not None:
                        event_log.emit(
                            EventType.CHECKPOINT,
                            world.timestep,
                            payload={"path": str(path), "population": world.population},
                        )

            metrics.compute(world, trace)
            if event_log is not None:
                event_log.emit(EventType.RUN_END, world.timestep, payload=world.stats())
        finally:
            if event_log is not None:
                event_log.close()

        elapsed = time.perf_counter() - started
        result = RunResult(
            run_id=run_id,
            world_id=world.world_id,
            label=label,
            seed=seed,
            config=config,
            steps=world.timestep,
            final_stats=world.stats(),
            metric_summary=metrics.summary(),
            metric_series=metrics.to_rows(),
            lineage_summary=world.lineage.summary(),
            acceleration=accelerator.summary(),
            events_path=str(run_dir.events_path) if self.write_events else None,
            trace=trace,
            extinct_at=world.extinct_at,
            wallclock_seconds=elapsed,
        )

        run_dir.write_json("summary.json", result.to_dict())
        self._write_metric_series(run_dir, metrics)
        self.progress.run_finished()
        if self.verbose:
            print(
                f"  {label:<20} seed {seed:<6} "
                f"pop {result.metric('population'):>6.0f}  "
                f"gen {result.metric('max_generation'):>4.0f}  "
                f"fitness {result.fitness():.4f}  ({elapsed:.1f}s)"
            )
        return result

    def _should_stop(self, world: World, steps: int, started: float) -> bool:
        if world.timestep >= steps:
            return True
        if world.config.stop.stop_on_extinction and not world.cells:
            return True
        limit = world.config.stop.max_wallclock_seconds
        return bool(limit and time.perf_counter() - started > limit)

    @staticmethod
    def _write_metric_series(run_dir: RunDirectory, metrics: MetricEngine) -> None:
        import json

        with open(run_dir.metrics_path, "w", encoding="utf-8") as handle:
            for row in metrics.to_rows():
                handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")))
                handle.write("\n")

    # -- batches --------------------------------------------------------------

    def run_many(
        self,
        jobs: list[tuple[SimulationConfig, str, int]],
        *,
        steps: int | None = None,
    ) -> list[RunResult]:
        """Run independent worlds, in parallel when workers allow.

        Results come back in submission order regardless of completion order, so
        a parallel run and a sequential one produce the same list.
        """
        if self.workers <= 1 or len(jobs) <= 1:
            return [
                self.run_world(config, label=label, seed=seed, steps=steps)
                for config, label, seed in jobs
            ]

        payloads = [
            (
                str(self.output_dir),
                config,
                label,
                seed,
                steps,
                self.write_events,
                self.keep_traces,
            )
            for config, label, seed in jobs
        ]

        results: list[RunResult | None] = [None] * len(payloads)
        try:
            with ProcessPoolExecutor(max_workers=min(self.workers, len(payloads))) as pool:
                futures = {
                    pool.submit(_run_world_task, payload): index
                    for index, payload in enumerate(payloads)
                }
                for future in as_completed(futures):
                    index = futures[future]
                    result = future.result()
                    results[index] = result
                    self.progress.run_finished()
                    if self.verbose:
                        print(
                            f"  {result.label:<20} seed {result.seed:<6} "
                            f"pop {result.metric('population'):>6.0f}  "
                            f"gen {result.metric('max_generation'):>4.0f}  "
                            f"fitness {result.fitness():.4f}  "
                            f"({result.wallclock_seconds:.1f}s)"
                        )
        except BrokenProcessPool as exc:
            # Nearly always the Windows spawn footgun: workers re-import the
            # calling module, so module-level code runs once per worker. The
            # default message names neither the cause nor the fix.
            raise RuntimeError(
                "Parallel workers died. On Windows and macOS a worker re-imports "
                "the module that started it, so a script calling ExperimentRunner "
                "must put its work behind `if __name__ == \"__main__\":` -- "
                "otherwise every worker re-runs the script itself. "
                "Pass workers=1 to run sequentially instead."
            ) from exc
        return [r for r in results if r is not None]

    def run_batch(
        self,
        configs: list[SimulationConfig],
        seeds: list[int],
        *,
        label: str = "treatment",
        steps: int | None = None,
    ) -> list[RunResult]:
        """Whitepaper section 10.1: many independent worlds, different seeds."""
        jobs = [(config, label, seed) for config in configs for seed in seeds]
        return self.run_many(jobs, steps=steps)

    def run_controls(
        self,
        config: SimulationConfig,
        control_names: list[str],
        seeds: list[int],
        *,
        steps: int | None = None,
    ) -> dict[str, list[RunResult]]:
        jobs: list[tuple[SimulationConfig, str, int]] = []
        for name in control_names:
            if name not in CONTROLS:
                raise ValueError(f"Unknown control '{name}'")
            controlled = apply_control(config, name)
            jobs.extend((controlled, name, seed) for seed in seeds)

        results = self.run_many(jobs, steps=steps)
        out: dict[str, list[RunResult]] = {name: [] for name in control_names}
        for (_, name, _), result in zip(jobs, results, strict=True):
            out[name].append(result)
        return out

    def run_experiment(
        self, spec, seeds: list[int], *, steps: int | None = None
    ) -> ExperimentReport:
        """Run one staged experiment: treatment arm, control arms, then detectors."""
        if self.verbose:
            print(f"\n{spec.experiment_id}  {spec.name}")
            print(f"  {spec.goal}")

        config = spec.build_config()
        steps = steps or config.stop.max_steps

        arms = 1 + len(spec.controls)
        self.progress.update(
            force=True,
            experiment=spec.experiment_id,
            runs_total=max(self.progress.progress.runs_total, arms * len(seeds)),
        )

        # Every arm goes into one pool: the control runs are as independent as
        # the treatment ones, and submitting them together keeps all the cores
        # busy instead of draining the pool once per arm.
        jobs: list[tuple[SimulationConfig, str, int]] = [
            (config, "treatment", seed) for seed in seeds
        ]
        for name in spec.controls:
            if name not in CONTROLS:
                raise ValueError(f"Unknown control '{name}'")
            controlled = apply_control(config, name)
            jobs.extend((controlled, name, seed) for seed in seeds)

        results = self.run_many(jobs, steps=steps)

        treatment: list[RunResult] = []
        controls: dict[str, list[RunResult]] = {name: [] for name in spec.controls}
        for (_, label, _), result in zip(jobs, results, strict=True):
            if label == "treatment":
                treatment.append(result)
            else:
                controls[label].append(result)

        detections = [
            d
            for d in run_all_detectors(treatment, controls)
            if not spec.detectors or d.name in spec.detectors or d.stage <= 1
        ]
        ladder = build_ladder(detections)

        report = ExperimentReport(
            experiment_id=spec.experiment_id,
            name=spec.name,
            goal=spec.goal,
            treatment=treatment,
            controls=controls,
            detections=detections,
            ladder=ladder.to_dict(),
            required=tuple(spec.detectors),
        )

        run_dir = RunDirectory.create(self.output_dir, f"{spec.experiment_id}-report")
        run_dir.write_json("report.json", report.to_dict())
        if self.verbose:
            print("\n".join(report.summary_lines()))
        return report
