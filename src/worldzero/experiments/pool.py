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
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty()
    if data.get("version") != VERSION:
        return empty()
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

    for experiment in summary.get("experiments", []):
        experiment_id = experiment.get("experiment_id")
        if not experiment_id:
            continue

        arms = _arms(experiment)
        # The design fingerprint deliberately excludes the seed: config_fingerprint
        # covers it, so keying on that would treat every run as a new design and
        # reset the pool on each one -- the guard would defeat the accumulation it
        # exists to protect. Controls differ from the treatment by design and carry
        # their own fingerprints, so the treatment arm identifies the world.
        treatment_runs = arms.get("treatment") or []
        fingerprint = ""
        if treatment_runs:
            first = treatment_runs[0]
            fingerprint = first.get("design_fingerprint") or first.get("config_fingerprint", "")

        entry = pool["experiments"].get(experiment_id)
        if entry is None or entry.get("fingerprint") != fingerprint:
            entry = {"fingerprint": fingerprint, "arms": {}}
            pool["experiments"][experiment_id] = entry

        new = 0
        for arm, runs in arms.items():
            stored = entry["arms"].setdefault(arm, {})
            for run in runs:
                seed = run.get("seed")
                fitness = run.get("fitness")
                if seed is None or fitness is None:
                    continue
                key = str(seed)
                if key not in stored:
                    new += 1
                stored[key] = float(fitness)
        added[experiment_id] = new

    return added


def arm_values(pool: dict[str, Any], experiment_id: str, arm: str) -> list[float]:
    entry = pool.get("experiments", {}).get(experiment_id, {})
    stored = entry.get("arms", {}).get(arm, {})
    return [stored[key] for key in sorted(stored, key=int)]


def sample_size(pool: dict[str, Any], experiment_id: str) -> int:
    return len(arm_values(pool, experiment_id, "treatment"))


def pooled_test(
    pool: dict[str, Any], experiment_id: str, control: str, *, seed: int = 0
) -> TestResult | None:
    treatment = arm_values(pool, experiment_id, "treatment")
    reference = arm_values(pool, experiment_id, control)
    if not treatment or not reference:
        return None
    return permutation_test(treatment, reference, seed=seed)


def provisional(pool: dict[str, Any], experiment_id: str) -> bool:
    return sample_size(pool, experiment_id) < TARGET_SEEDS
