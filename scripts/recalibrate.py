"""Re-calibrate the experiments where selection stopped operating.

The 08-19 pass targeted viability alone and overshot: E6 and E7 became rich
enough that a random-action population outscored an evolved one, which is
section 19's *other* named failure ("no adaptation"). Fixing "all cells die
quickly" walked straight into it. The target is the band between the two, so
viability is now two-sided and both halves are fixed before any detector runs:

  SURVIVES  alive at the end on every seed, max_generation >= 10
  SELECTS   evolved fitness > random-action fitness on a majority of seeds

Only carrying-capacity fields are touched. E1 also varies its run length,
because `static` food is terminal by design and the question there is which
window holds a living, still-evolving population.

    python scripts/recalibrate.py [--workers N]
"""

from __future__ import annotations

import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from worldzero.core.world import World
from worldzero.experiments.controls import apply_control
from worldzero.experiments.runner import resolve_workers
from worldzero.experiments.suite import SUITE
from worldzero.storage.progress import ProgressReporter

BASE = {"world": {"width": 64, "height": 64}, "cell": {"start_population": 200}}
SEEDS = [1, 2, 3]
MIN_GENERATION = 10
PROGRESS = Path("outputs/recalibrate/progress.json")

CANDIDATES: dict[str, list[dict]] = {
    # E6/E7 were over-supplied; step coverage back down toward scarcity.
    "E6": [
        {"resources": {"initial_density": d, "regen_rate": r}}
        for d, r in ((0.16, 0.1), (0.12, 0.07), (0.10, 0.05), (0.08, 0.04))
    ],
    "E7": [
        {"resources": {"initial_density": d, "regen_rate": r}}
        for d, r in ((0.6, 0.4), (0.4, 0.25), (0.3, 0.18), (0.25, 0.12), (0.2, 0.08))
    ],
    # E1 is terminal by design: vary the measurement window, not just the food.
    "E1": [
        {"resources": {"initial_density": d}, "stop": {"max_steps": s}}
        for d, s in ((0.12, 250), (0.12, 400), (0.2, 600), (0.3, 900), (0.3, 1500))
    ],
}


def _one_world(payload: tuple[str, dict, int, bool]) -> dict:
    """Worker: run a single world and report what the criterion needs."""
    experiment_id, override, seed, random_actions = payload
    config = SUITE[experiment_id].build_config(BASE).merged(override).with_seed(seed)
    if random_actions:
        config = apply_control(config, "random")

    world = World(config)
    for _ in range(config.stop.max_steps):
        world.step()
        if not world.cells:
            break

    alive = bool(world.cells)
    lifespan = world.lineage.mean_lifespan()
    fitness = (
        lifespan * max(1.0, world.population) / max(1.0, float(world.timestep)) if alive else 0.0
    )
    return {
        "seed": seed,
        "random": random_actions,
        "alive": alive,
        "generation": world.lineage.max_generation(),
        "population": world.population,
        "timestep": world.timestep,
        "fitness": fitness,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=0)
    args = parser.parse_args()
    workers = resolve_workers(args.workers)

    jobs: list[tuple[str, dict, int, bool]] = []
    for experiment_id, options in CANDIDATES.items():
        for override in options:
            for seed in SEEDS:
                jobs.append((experiment_id, override, seed, False))
                jobs.append((experiment_id, override, seed, True))

    print(f"{len(jobs)} worlds across {workers} workers\n")
    started = time.perf_counter()

    with ProgressReporter(PROGRESS, command="recalibrate") as progress:
        progress.update(runs_total=len(jobs), force=True)
        outcomes: list[dict] = []
        with ProcessPoolExecutor(max_workers=workers) as pool:
            for job, outcome in zip(jobs, pool.map(_one_world, jobs), strict=True):
                outcomes.append({"experiment": job[0], "override": job[1], **outcome})
                progress.run_finished()

    elapsed = time.perf_counter() - started
    print(f"finished in {elapsed / 60:.1f} min\n")

    # Fold the flat results back into per-candidate verdicts.
    chosen: dict[str, dict] = {}
    print(f"{'exp':<4} {'override':<50} {'survives':>9} {'selects':>8}  detail")
    print("-" * 116)

    for experiment_id, options in CANDIDATES.items():
        for override in options:
            if experiment_id in chosen:
                break
            rows = [
                o
                for o in outcomes
                if o["experiment"] == experiment_id and o["override"] == override
            ]
            evolved = {o["seed"]: o for o in rows if not o["random"]}
            baseline = {o["seed"]: o for o in rows if o["random"]}

            survives = all(
                evolved[s]["alive"] and evolved[s]["generation"] >= MIN_GENERATION
                for s in SEEDS
            )
            wins = sum(1 for s in SEEDS if evolved[s]["fitness"] > baseline[s]["fitness"])
            selects = wins >= 2

            detail = " ".join(
                f"s{s}:{'pop' + str(evolved[s]['population']) if evolved[s]['alive'] else 'dead'}"
                f"/g{evolved[s]['generation']}"
                f"/{evolved[s]['fitness']:.1f}v{baseline[s]['fitness']:.1f}"
                for s in SEEDS
            )
            label = "; ".join(f"{k}={v}" for k, v in override.items())
            print(
                f"{experiment_id:<4} {label:<50} {str(survives):>9} {str(selects):>8}  {detail}"
            )
            if survives and selects:
                chosen[experiment_id] = override

    print("\n\nCHOSEN")
    for experiment_id, override in chosen.items():
        print(f"  {experiment_id}: {override}")
    missing = [e for e in CANDIDATES if e not in chosen]
    print(f"  UNRESOLVED: {missing}" if missing else "  all resolved")

    PROGRESS.parent.mkdir(parents=True, exist_ok=True)
    (PROGRESS.parent / "result.json").write_text(
        json.dumps({"chosen": chosen, "outcomes": outcomes}, indent=2, default=str),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
