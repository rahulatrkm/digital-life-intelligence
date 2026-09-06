"""Pool suite runs across days so evidence accumulates instead of repeating.

The daily job ran the default seeds every time. The engine is deterministic, so
identical seeds against an identical config reproduce identical numbers: five
consecutive daily reports agreed to four significant figures because they were
one computation repeated, not five replications of it. Re-running a
deterministic function is not evidence.

Runs now contribute fresh seeds and land here. Two rules keep the pooling
honest:

* Only runs sharing a config fingerprint may be pooled. A config change starts
  that experiment's pool over rather than averaging across different worlds.
  The fingerprint is already recorded on every run.
* Observations are keyed by seed, so re-running a seed overwrites it. Appending
  instead would let a repeated run inflate the sample and manufacture power out
  of the same numbers counted twice -- the exact failure this module exists to
  end.
"""

from __future__ import annotations

import json
from copy import deepcopy
from math import isfinite
from pathlib import Path
from typing import Any

from worldzero.metrics.information import TestResult, permutation_test

VERSION = 1

TARGET_SEEDS = 30
"""Seeds per arm, fixed ahead of the data.

Testing a growing sample every day and stopping at the first p < 0.05 reaches
significance by chance sooner or later, so the stopping point cannot be chosen
once the numbers are visible. At 30 against 30 the permutation test resolves
far past 0.05, and the effects left open at 5 seeds -- E4 at d = 0.754, E5 at
d = 0.727 -- carry roughly 0.89 power one-sided. Below this a comparison is
reported as provisional however pretty its p-value looks.
"""


def empty() -> dict[str, Any]:
    return {"version": VERSION, "experiments": {}}


def load(path: Path) -> dict[str, Any]:
    if not path.exists():
        return empty()
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("version") != VERSION:
        raise ValueError(f"Unsupported evidence pool version at {path}; refusing to discard it")
    if not isinstance(data.get("experiments"), dict):
        raise ValueError(f"Invalid evidence pool at {path}")
    return data


def save(path: Path, pool: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(f".{path.suffix}.tmp")
    temp.write_text(json.dumps(pool, indent=2, sort_keys=True), encoding="utf-8")
    temp.replace(path)


def _arms(experiment: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    arms: dict[str, list[dict[str, Any]]] = {"treatment": experiment.get("treatment") or []}
    for name, runs in (experiment.get("controls") or {}).items():
        arms[name] = runs or []
    return arms


def merge_summary(pool: dict[str, Any], summary: dict[str, Any]) -> dict[str, int]:
    """Fold one suite summary into the pool, returning new observations per experiment."""
    added: dict[str, int] = {}
    updated = deepcopy(pool)

    for experiment in summary.get("experiments", []):
        experiment_id = experiment.get("experiment_id")
        if not experiment_id:
            continue

        arms = _arms(experiment)
        fingerprints = {}
        for arm, runs in arms.items():
            designs = {run.get("design_fingerprint") for run in runs}
            if len(designs) != 1 or not next(iter(designs), None):
                raise ValueError(f"{experiment_id}/{arm}: missing or mixed design fingerprints")
            fingerprints[arm] = next(iter(designs))
            for run in runs:
                fitness = run.get("fitness")
                if not isinstance(run.get("seed"), int):
                    raise ValueError(f"{experiment_id}/{arm}: invalid seed or fitness")
                if not isinstance(fitness, (int, float)) or not isfinite(fitness):
                    raise ValueError(f"{experiment_id}/{arm}: invalid fitness")

        fingerprint = fingerprints["treatment"]
        entry = updated["experiments"].get(experiment_id)
        changed = entry is not None and (
            entry.get("fingerprint") != fingerprint
            or set(entry["arms"]) != set(arms)
            or entry.get("arm_fingerprints", fingerprints) != fingerprints
        )
        if changed:
            updated.setdefault("archives", {}).setdefault(experiment_id, []).append(entry)
        if entry is None or changed:
            entry = {"fingerprint": fingerprint, "arms": {}}
            updated["experiments"][experiment_id] = entry
        entry["arm_fingerprints"] = fingerprints

        new = 0
        for arm, runs in arms.items():
            stored = entry["arms"].setdefault(arm, {})
            for run in runs:
                seed = run.get("seed")
                fitness = run.get("fitness")
                if seed is None or fitness is None:
                    continue
                key = str(seed)
                if key in stored and stored[key] != float(fitness):
                    raise ValueError(f"{experiment_id}/{arm}: conflicting result for seed {seed}")
                if key not in stored:
                    new += 1
                stored[key] = float(fitness)
        selected = analysis_seeds(updated, experiment_id)
        if len(selected) == TARGET_SEEDS:
            entry.setdefault("cohort_seeds", selected)
        added[experiment_id] = new

    pool.clear()
    pool.update(updated)
    return added


def arm_values(pool: dict[str, Any], experiment_id: str, arm: str) -> list[float]:
    entry = pool.get("experiments", {}).get(experiment_id, {})
    stored = entry.get("arms", {}).get(arm, {})
    return [stored[key] for key in sorted(stored, key=int)]


def sample_size(pool: dict[str, Any], experiment_id: str) -> int:
    return len(analysis_seeds(pool, experiment_id))


def analysis_seeds(pool: dict[str, Any], experiment_id: str) -> list[int]:
    """Use complete matched seeds and freeze the first target-sized cohort."""
    entry = pool.get("experiments", {}).get(experiment_id, {})
    if "cohort_seeds" in entry:
        return list(entry["cohort_seeds"])
    arms = entry.get("arms", {})
    if not arms or not arms.get("treatment"):
        return []
    common = set.intersection(*(set(map(int, observations)) for observations in arms.values()))
    if "study" in pool:
        common.intersection_update(pool["study"]["seeds"])
    return sorted(common)[:TARGET_SEEDS]


def complete(pool: dict[str, Any], experiments: list[str]) -> bool:
    return bool(experiments) and all(
        sample_size(pool, experiment_id) == TARGET_SEEDS for experiment_id in experiments
    )


def pooled_test(
    pool: dict[str, Any], experiment_id: str, control: str, *, seed: int = 0
) -> TestResult | None:
    arms = pool.get("experiments", {}).get(experiment_id, {}).get("arms", {})
    seeds = analysis_seeds(pool, experiment_id)
    if not seeds or control not in arms:
        return None
    treatment = [arms["treatment"][str(seed)] for seed in seeds]
    reference = [arms[control][str(seed)] for seed in seeds]
    return permutation_test(treatment, reference, seed=seed)


def provisional(pool: dict[str, Any], experiment_id: str) -> bool:
    return sample_size(pool, experiment_id) < TARGET_SEEDS
