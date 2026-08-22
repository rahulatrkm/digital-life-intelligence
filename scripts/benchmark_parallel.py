"""Measure the parallel speedup on a real experiment.

The __main__ guard is not optional. Windows spawns workers by re-importing this
module, so unguarded module-level code runs once per worker -- which here meant
eight workers each deleting the output directory the parent was writing to.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path

from worldzero.experiments.runner import ExperimentRunner, resolve_workers
from worldzero.experiments.suite import get_experiment

SEEDS = [1, 2, 3, 4, 5]
STEPS = 1200
ROOT = Path("outputs/bench")


def main() -> None:
    spec = get_experiment("E0")
    arms = 1 + len(spec.controls)

    if ROOT.exists():
        shutil.rmtree(ROOT)

    print(f"E0: {arms} arms x {len(SEEDS)} seeds = {arms * len(SEEDS)} runs of {STEPS} steps")
    print(f"auto workers = {resolve_workers(0)}\n")

    timings: dict[int, float] = {}
    fingerprints: dict[int, list] = {}

    for workers in (1, 0):
        label = "sequential" if workers == 1 else f"parallel x{resolve_workers(0)}"
        runner = ExperimentRunner(
            ROOT / f"w{workers}", write_events=False, keep_traces=True, workers=workers
        )
        started = time.perf_counter()
        report = runner.run_experiment(spec, SEEDS, steps=STEPS)
        elapsed = time.perf_counter() - started

        timings[workers] = elapsed
        fingerprints[workers] = [r.final_stats for r in report.treatment]
        print(f"{label:<16} {elapsed:>7.1f}s")

    print(f"\nspeedup: {timings[1] / timings[0]:.2f}x")
    print(f"identical results: {fingerprints[1] == fingerprints[0]}")

    shutil.rmtree(ROOT, ignore_errors=True)


if __name__ == "__main__":
    main()
