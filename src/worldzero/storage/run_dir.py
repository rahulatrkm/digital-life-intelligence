"""Run directory layout and containment (whitepaper sections 12.3 and 20).

Section 20 requires that nothing an evolved organism does can write outside the
experiment directory. Cells never touch the filesystem at all in this build, so
the practical job here is to make every writer resolve its paths through one
root and refuse anything that escapes it.
"""

from __future__ import annotations

import json
import platform
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ContainmentError(RuntimeError):
    """Raised when a write would land outside the run directory."""


@dataclass
class RunDirectory:
    root: Path
    run_id: str

    @classmethod
    def create(
        cls,
        base: str | Path,
        run_id: str,
        *,
        exist_ok: bool = True,
    ) -> RunDirectory:
        root = (Path(base) / run_id).resolve()
        root.mkdir(parents=True, exist_ok=exist_ok)
        (root / "checkpoints").mkdir(exist_ok=True)
        (root / "metrics").mkdir(exist_ok=True)
        (root / "detections").mkdir(exist_ok=True)
        return cls(root=root, run_id=run_id)

    def path(self, *parts: str) -> Path:
        target = self.root.joinpath(*parts).resolve()
        if target != self.root and self.root not in target.parents:
            raise ContainmentError(f"Refusing to write outside the run directory: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        return target

    @property
    def events_path(self) -> Path:
        return self.path("events.jsonl")

    @property
    def config_path(self) -> Path:
        return self.path("config.yaml")

    @property
    def metrics_path(self) -> Path:
        return self.path("metrics", "series.jsonl")

    @property
    def summary_path(self) -> Path:
        return self.path("summary.json")

    def checkpoint_path(self, timestep: int) -> Path:
        return self.path("checkpoints", f"step_{timestep:012d}.json.gz")

    def write_json(self, name: str, data: Any) -> Path:
        target = self.path(name)
        target.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        return target

    def write_provenance(self, config: Any, seed: int) -> Path:
        """Section 20: record complete provenance for any run used in claims."""
        from worldzero import __version__

        provenance = {
            "run_id": self.run_id,
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "code_version": __version__,
            "config_fingerprint": config.fingerprint(),
            "seed": seed,
            "python": sys.version,
            "platform": platform.platform(),
            "git_commit": _git_commit(),
        }
        return self.write_json("provenance.json", provenance)


def _git_commit() -> str | None:
    """Best-effort commit id; absent in a source tarball and that is fine."""
    import subprocess

    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
            cwd=Path(__file__).resolve().parent,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() or None if result.returncode == 0 else None
