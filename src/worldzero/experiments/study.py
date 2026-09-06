"""A resumable fixed-size study; fitness comparisons are not stage verdicts."""

from __future__ import annotations

import json
from pathlib import Path
from statistics import median
from typing import Any

from worldzero.core.config import SimulationConfig
from worldzero.experiments import pool as pooling
from worldzero.experiments.controls import apply_control
from worldzero.experiments.runner import ExperimentRunner
from worldzero.experiments.suite import SUITE, ExperimentSpec
from worldzero.results import RunResult
from worldzero.storage.progress import ProgressReporter
from worldzero.storage.result_cache import simulation_fingerprint

FIRST_SEED = 6
FITNESS_CONTROLS = {
    "E2": "scrambled_memory",
    "E3": "no_memory",
    "E4": "scrambled_signals",
    "E5": "isolated",
    "E6": "single_variant",
    "E7": "no_markers",
    "E8": "no_probe",
}


def arm_configs(spec: ExperimentSpec) -> dict[str, SimulationConfig]:
    config = spec.build_config()
    return {"treatment": config} | {
        name: apply_control(config, name) for name in spec.controls
    }


def recover(
    pool: dict[str, Any], output: Path, specs: dict[str, ExperimentSpec] = SUITE
) -> dict[str, int]:
    """Recover config-validated measurements, never invent missing behavior traces."""
    if "study" in pool:
        ensure_plan(pool, specs)
    recovered = {}
    for experiment_id, spec in specs.items():
        arms = {}
        sources = {}
        for arm, expected in arm_configs(spec).items():
            runs = []
            for path in sorted(output.glob(f"{expected.name}-{arm}-s*/summary.json")):
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    pool.setdefault("recovery_warnings", {})[str(path)] = "incomplete summary"
                    continue
                seed = data.get("seed")
                if not isinstance(seed, int) or seed < FIRST_SEED:
                    continue
                config_path = path.parent / "config.yaml"
                if not config_path.exists():
                    continue
                try:
                    saved = SimulationConfig.from_yaml(config_path)
                except (OSError, ValueError):
                    pool.setdefault("recovery_warnings", {})[str(path)] = "invalid saved config"
                    continue
                wanted = expected.with_seed(seed)
                if saved.fingerprint() != wanted.fingerprint():
                    continue
                if (
                    data.get("config_fingerprint") != saved.fingerprint()
                    or data.get("label") != arm
                ):
                    continue
                if data["steps"] < wanted.stop.max_steps and data.get("extinct_at") is None:
                    continue
                if saved.stop.max_wallclock_seconds:
                    continue
                data["design_fingerprint"] = wanted.design_fingerprint()
                runs.append(data)
                sources[f"{arm}/{seed}"] = str(path.resolve())
            arms[arm] = runs
            costs = [
                run["wallclock_seconds"] for run in runs if run.get("wallclock_seconds", 0) > 0
            ]
            if costs:
                estimates = pool.setdefault("cost_estimates", {}).setdefault(experiment_id, {})
                estimates[arm] = median(costs)
        if not all(arms.values()):
            continue
        recovered.update(pooling.merge_summary(pool, {"experiments": [{
            "experiment_id": experiment_id,
            "treatment": arms.pop("treatment"),
            "controls": arms,
        }]}))
        pool["experiments"][experiment_id]["recovered_sources"] = sources
    return recovered


def ensure_plan(pool: dict[str, Any], specs: dict[str, ExperimentSpec] = SUITE) -> list[int]:
    if "study" in pool:
        plan = pool["study"]
        if plan["target_seeds"] != pooling.TARGET_SEEDS or plan["experiments"] != list(specs):
            raise ValueError("Existing study plan differs; archive it before starting a new study")
        expected = plan.setdefault("simulation_fingerprint", simulation_fingerprint())
        if expected != simulation_fingerprint():
            raise ValueError("Simulation code changed; preserve this cohort and start a new study")
        return list(plan["seeds"])
    observed = {
        int(seed)
        for experiment_id in specs
        for arm in pool.get("experiments", {}).get(experiment_id, {}).get("arms", {}).values()
        for seed in arm
        if int(seed) >= FIRST_SEED
    }
    seeds = sorted(observed)[:pooling.TARGET_SEEDS]
    candidate = max(seeds, default=FIRST_SEED - 1) + 1
    while len(seeds) < pooling.TARGET_SEEDS:
        seeds.append(candidate)
        candidate += 1
    pool["study"] = {
        "target_seeds": pooling.TARGET_SEEDS,
        "seeds": seeds,
        "experiments": list(specs),
        "scope": "fixed-cohort fitness comparisons, not a full pooled intelligence ladder",
        "simulation_fingerprint": simulation_fingerprint(),
    }
    return seeds


def pending_jobs(
    pool: dict[str, Any], specs: dict[str, ExperimentSpec] = SUITE,
    *, per_experiment: int | None = None,
) -> list[tuple[str, SimulationConfig, str, int]]:
    seeds = ensure_plan(pool, specs)
    jobs = []
    for experiment_id, spec in specs.items():
        entry = pool.get("experiments", {}).get(experiment_id, {})
        configs = arm_configs(spec)
        if entry and entry["fingerprint"] != configs["treatment"].design_fingerprint():
            raise ValueError(f"{experiment_id}: study design changed")
        missing = [seed for seed in seeds if any(
            str(seed) not in entry.get("arms", {}).get(arm, {}) for arm in configs
        )]
        if per_experiment is not None:
            missing = missing[:per_experiment]
        for arm, config in configs.items():
            stored_design = entry.get("arm_fingerprints", {}).get(arm)
            if stored_design and stored_design != config.design_fingerprint():
                raise ValueError(f"{experiment_id}/{arm}: study control changed")
            jobs.extend(
                (experiment_id, config, arm, seed)
                for seed in missing if str(seed) not in entry.get("arms", {}).get(arm, {})
            )
    costs = pool.get("cost_estimates", {})
    return sorted(jobs, key=lambda job: costs.get(job[0], {}).get(job[2], 0), reverse=True)


def run_pending(
    pool: dict[str, Any], pool_path: Path, output: Path,
    *, workers: int = 0, per_experiment: int | None = None,
    progress: ProgressReporter | None = None, specs: dict[str, ExperimentSpec] = SUITE,
) -> int:
    jobs = pending_jobs(pool, specs, per_experiment=per_experiment)
    if not jobs:
        return 0
    progress = progress or ProgressReporter(None)
    progress.update(force=True, runs_total=len(jobs), phase="fixed-cohort study")
    pending = {}
    for experiment_id, spec in specs.items():
        existing = pool.get("experiments", {}).get(experiment_id, {}).get("arms", {})
        pending[experiment_id] = {
            arm: [{"seed": int(seed), "fitness": fitness,
                   "design_fingerprint": config.design_fingerprint()}
                  for seed, fitness in existing.get(arm, {}).items()]
            for arm, config in arm_configs(spec).items()
        }
    owners = {(config.name, arm, seed): experiment_id
              for experiment_id, config, arm, seed in jobs}

    def record(result: RunResult) -> None:
        experiment_id = owners[(result.config.name, result.label, result.seed)]
        arms = pending[experiment_id]
        arms[result.label].append(result.to_dict())
        if all(arms.values()):
            pooling.merge_summary(pool, {"experiments": [{
                "experiment_id": experiment_id,
                "treatment": arms["treatment"],
                "controls": {arm: runs for arm, runs in arms.items() if arm != "treatment"},
            }]})
            pooling.save(pool_path, pool)
        progress.update(force=True, experiment=experiment_id, seed=result.seed, label=result.label)

    runner = ExperimentRunner(
        output, workers=workers, write_events=False, keep_traces=True,
        reuse_completed=True, progress=progress,
    )
    runner.run_many(
        [(config, arm, seed) for _, config, arm, seed in jobs],
        on_result=record, retain_results=False,
    )
    return len(jobs)