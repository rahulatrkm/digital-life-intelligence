"""Where does suite wall-clock actually go?

Reads the per-run summary.json files a suite leaves behind, so the figures are
measured rather than estimated.

    python scripts/timing_report.py outputs/suite-v5
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

root = Path(sys.argv[1] if len(sys.argv) > 1 else "outputs/suite-v5")
if not root.exists():
    raise SystemExit(f"no such directory: {root}")

by_experiment: dict[str, list[float]] = defaultdict(list)
by_arm: dict[tuple[str, str], list[float]] = defaultdict(list)
steps_by_experiment: dict[str, int] = {}

for summary in root.glob("*/summary.json"):
    try:
        data = json.loads(summary.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        continue
    run_id = data.get("run_id", summary.parent.name)
    experiment = run_id.split("-")[0].upper()
    seconds = float(data.get("wallclock_seconds", 0.0))
    by_experiment[experiment].append(seconds)
    by_arm[(experiment, data.get("label", "?"))].append(seconds)
    steps_by_experiment[experiment] = max(
        steps_by_experiment.get(experiment, 0), int(data.get("steps", 0))
    )

if not by_experiment:
    raise SystemExit(f"no run summaries under {root}")

total_cpu = sum(sum(v) for v in by_experiment.values())
print(f"suite: {root}")
print(f"{sum(len(v) for v in by_experiment.values())} worlds, "
      f"{total_cpu / 60:.1f} min of CPU\n")

print(f"{'exp':<5} {'worlds':>6} {'steps':>7} {'cpu min':>8} {'share':>6} "
      f"{'mean s':>8} {'slowest':>8}")
print("-" * 60)
for experiment in sorted(by_experiment, key=lambda e: -sum(by_experiment[e])):
    times = by_experiment[experiment]
    cpu = sum(times)
    print(
        f"{experiment:<5} {len(times):>6} {steps_by_experiment[experiment]:>7} "
        f"{cpu / 60:>8.1f} {100 * cpu / total_cpu:>5.1f}% "
        f"{cpu / len(times):>8.1f} {max(times):>8.1f}"
    )

print("\nslowest arms (control arms often cost more than the treatment):")
ranked = sorted(by_arm.items(), key=lambda kv: -sum(kv[1]))[:8]
for (experiment, arm), times in ranked:
    print(f"  {experiment:<4} {arm:<20} {sum(times) / 60:>6.1f} min  "
          f"({len(times)} runs, {sum(times) / len(times):.0f}s each)")

workers = 8
print(f"\nwall-clock estimate at {workers} workers: {total_cpu / workers / 60:.1f} min")
print(f"  (perfect scaling; the tail is bounded by the slowest single world: "
      f"{max(max(v) for v in by_experiment.values()) / 60:.1f} min)")
