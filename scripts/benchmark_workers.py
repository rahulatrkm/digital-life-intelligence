"""Does raising the worker cap past the physical core count help?

The step loop is pure Python, so it may benefit from SMT threads that a
float-saturating workload would not. That is a hypothesis, not a fact, so
measure it rather than assume either way.

Run on an otherwise idle machine.

    python scripts/benchmark_workers.py
"""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path

from worldzero.experiments.runner import ExperimentRunner
from worldzero.experiments.suite import get_experiment

ROOT = Path("outputs/worker-bench")
SEEDS = list(range(1, 13))
STEPS = 1500


def main() -> None:
    logical = os.cpu_count() or 2
    counts = sorted({4, 8, max(1, logical - 1), logical})
    spec = get_experiment("E0")
    jobs = (1 + len(spec.controls)) * len(SEEDS)

    print(f"{logical} logical processors, {jobs} worlds of {STEPS} steps per trial\n")
    print(f"{'workers':>8} {'seconds':>9} {'speedup':>9} {'per world':>10}")
    print("-" * 40)

    baseline = None
    results = {}
    for workers in counts:
        if ROOT.exists():
            shutil.rmtree(ROOT)
        runner = ExperimentRunner(
            ROOT, write_events=False, keep_traces=True, workers=workers
        )
        started = time.perf_counter()
        report = runner.run_experiment(spec, SEEDS, steps=STEPS)
        elapsed = time.perf_counter() - started

        baseline = baseline or elapsed
        results[workers] = (elapsed, [r.final_stats for r in report.treatment])
        print(
            f"{workers:>8} {elapsed:>9.1f} {baseline / elapsed:>8.2f}x "
            f"{elapsed / jobs:>9.2f}s"
        )

    reference = results[counts[0]][1]
    identical = all(stats == reference for _, stats in results.values())
    print(f"\nidentical results across worker counts: {identical}")

    best = min(results, key=lambda w: results[w][0])
    print(f"fastest: {best} workers")
    if best <= 8 < logical:
        print("SMT threads do not help this workload; keep the cap at the core count.")
    else:
        print("SMT threads do help; the cap should follow the logical processor count.")

    shutil.rmtree(ROOT, ignore_errors=True)


if __name__ == "__main__":
    main()
