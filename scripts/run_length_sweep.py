"""Is the E2 memory null a real absence, or just too little evolutionary time?

E2 runs 4000 steps and reaches roughly generation 50. E9 runs 12000 and reaches
253. A mechanism that needs hundreds of generations to appear would look
identical to one that never appears, so the two have to be separated.

This is a dose-response test, not another attempt to make E2 pass: run the same
experiment at increasing lengths and watch the effect size. If memory is
slowly emerging, d rises with run length. If d stays near zero however long the
world runs, the null is about the mechanism rather than the clock.

Nothing is tuned -- only stop.max_steps changes.

    python scripts/run_length_sweep.py [--seeds N]
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from worldzero.experiments.runner import ExperimentRunner
from worldzero.experiments.suite import get_experiment

LENGTHS = [4000, 16000]
OUTPUT = Path("outputs/run-length")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seeds", type=int, default=6)
    parser.add_argument("--experiment", default="E2")
    args = parser.parse_args()

    seeds = list(range(1, args.seeds + 1))
    spec = get_experiment(args.experiment)
    rows = []

    print(f"{args.experiment}: {args.seeds} seeds, lengths {LENGTHS}")
    print(f"{'steps':>7} {'gen':>6} {'pop':>7} {'d':>8} {'p':>8}  criterion")
    print("-" * 74)

    for steps in LENGTHS:
        started = time.perf_counter()
        runner = ExperimentRunner(
            OUTPUT / str(steps), write_events=False, keep_traces=True, workers=0
        )
        report = runner.run_experiment(spec, seeds, steps=steps)

        target = next(
            (d for d in report.detections if d.name in spec.detectors), None
        )
        test = (target.evidence or {}).get("test", {}) if target else {}
        generation = sum(r.metric("max_generation") for r in report.treatment) / len(
            report.treatment
        )
        population = sum(r.metric("population") for r in report.treatment) / len(
            report.treatment
        )
        criterion = next(
            (c.detail for c in (target.criteria if target else []) if not c.passed),
            "all passed",
        )

        rows.append(
            {
                "steps": steps,
                "generation": round(generation, 1),
                "population": round(population, 1),
                "effect_size": test.get("effect_size"),
                "p_value": test.get("p_value"),
                "detected": bool(target and target.detected),
                "minutes": round((time.perf_counter() - started) / 60, 1),
            }
        )
        print(
            f"{steps:>7} {generation:>6.0f} {population:>7.0f} "
            f"{test.get('effect_size', float('nan')):>8.3f} "
            f"{test.get('p_value', float('nan')):>8.4f}  {criterion[:44]}"
        )

    OUTPUT.mkdir(parents=True, exist_ok=True)
    (OUTPUT / "result.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")

    first, last = rows[0], rows[-1]
    if first["effect_size"] is not None and last["effect_size"] is not None:
        direction = "rises" if last["effect_size"] > first["effect_size"] else "does not rise"
        print(
            f"\neffect size {direction} with run length "
            f"({first['effect_size']:.3f} at {first['steps']} -> "
            f"{last['effect_size']:.3f} at {last['steps']}), "
            f"generations {first['generation']:.0f} -> {last['generation']:.0f}"
        )


if __name__ == "__main__":
    main()
