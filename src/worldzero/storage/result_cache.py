"""Validated, detector-complete results for restarting interrupted batches."""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import sys
from dataclasses import fields
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from worldzero.core.config import SimulationConfig
from worldzero.metrics.traces import BehaviorTrace, TraceSample
from worldzero.results import RunResult

FORMAT_VERSION = 1
SAMPLE_FIELDS = tuple(item.name for item in fields(TraceSample))


@lru_cache(maxsize=1)
def simulation_fingerprint() -> str:
    root = Path(__file__).resolve().parents[1]
    paths = [root / "results.py"]
    for directory in ("core", "genome", "environments", "metrics"):
        paths.extend(sorted((root / directory).glob("*.py")))
    digest = hashlib.sha256()
    digest.update(f"{sys.version_info[:3]}:{np.__version__}".encode())
    for path in paths:
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


@lru_cache(maxsize=1)
def engine_fingerprint() -> str:
    root = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256(simulation_fingerprint().encode())
    for path in (root / "experiments" / "runner.py", Path(__file__)):
        digest.update(path.read_bytes())
    return digest.hexdigest()


def cache_path(
    output: Path,
    config: SimulationConfig,
    label: str,
    steps: int,
    keep_traces: bool,
    write_events: bool,
) -> Path:
    identity = [
        FORMAT_VERSION, engine_fingerprint(), config.fingerprint(),
        label, steps, keep_traces, write_events,
    ]
    key = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    return output / ".result-cache" / f"{key}.json.gz"


def _trace_data(trace: BehaviorTrace | None) -> dict[str, Any] | None:
    if trace is None:
        return None
    return {
        "max_samples": trace.max_samples,
        "max_cells_per_sample": trace.max_cells_per_sample,
        "samples": [[getattr(sample, name) for name in SAMPLE_FIELDS] for sample in trace.samples],
        "tile_future": [[*key, value] for key, value in trace.tile_future.items()],
        "signal_observations": trace.signal_observations,
        "truncated": trace.truncated,
    }


def save_result(path: Path, result: RunResult) -> None:
    data = result.to_dict()
    data["metric_series"] = result.metric_series
    data["wallclock_seconds"] = result.wallclock_seconds
    data["trace"] = _trace_data(result.trace)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        with gzip.open(temporary, "wt", encoding="utf-8", compresslevel=1) as handle:
            json.dump(data, handle, separators=(",", ":"), allow_nan=False)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def load_result(path: Path, config: SimulationConfig) -> RunResult | None:
    if not path.exists():
        return None
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            data = json.load(handle)
        if data["config_fingerprint"] != config.fingerprint():
            return None
        trace = None
        if data["trace"] is not None:
            stored = data["trace"]
            samples = []
            for row in stored["samples"]:
                values = dict(zip(SAMPLE_FIELDS, row, strict=True))
                values["memory"] = tuple(values["memory"])
                samples.append(TraceSample(**values))
            trace = BehaviorTrace(
                max_samples=stored["max_samples"],
                max_cells_per_sample=stored["max_cells_per_sample"],
                samples=samples,
                tile_future={tuple(row[:3]): row[3] for row in stored["tile_future"]},
                signal_observations=[tuple(row) for row in stored["signal_observations"]],
                truncated=stored["truncated"],
            )
        return RunResult(
            config=config,
            trace=trace,
            **{name: data[name] for name in (
                "run_id", "world_id", "label", "seed", "steps", "final_stats",
                "metric_summary", "metric_series", "lineage_summary", "acceleration",
                "events_path", "extinct_at", "wallclock_seconds",
            )},
        )
    except (OSError, EOFError, ValueError, KeyError, TypeError):
        return None