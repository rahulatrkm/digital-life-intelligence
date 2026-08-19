"""Build the reference checkpoint committed to the repository.

Deterministic and regenerable: same config, same seed, same bytes. Kept small
on purpose -- a 32x32 world gzips to a few tens of KB, which git can carry
without the history bloat a full-size run would cause.

    python scripts/make_reference_checkpoint.py
"""

from __future__ import annotations

from pathlib import Path

from worldzero.core.config import SimulationConfig
from worldzero.core.world import World
from worldzero.storage.checkpoints import load_checkpoint, save_checkpoint

TARGET = Path(__file__).resolve().parents[1] / "reference" / "world_zero_step2000.json.gz"
STEPS = 2000

CONFIG = {
    "world": {"width": 32, "height": 32, "seed": 42},
    "cell": {"start_population": 80, "max_sensor_stage": 1},
    "resources": {"regime": "regenerating", "initial_density": 0.16, "regen_rate": 0.1},
    "hazards": {"regime": "static"},
    "logging": {"metrics_interval": 200, "trace_interval": 50, "checkpoint_interval": 0},
    "stop": {"max_steps": STEPS},
}


def main() -> None:
    config = SimulationConfig(name="world_zero_reference").merged(CONFIG)
    world = World(config, run_id="reference", world_id="reference")

    for _ in range(STEPS):
        world.step()
        if not world.cells:
            raise SystemExit(f"reference world went extinct at step {world.timestep}")

    path = save_checkpoint(world, TARGET)
    restored = load_checkpoint(path)
    if restored.stats() != world.stats():
        raise SystemExit("checkpoint did not round-trip; refusing to write a broken reference")

    print(f"wrote {path} ({path.stat().st_size / 1024:.0f}K)")
    print(f"  step {world.timestep}  pop {world.population}  "
          f"gen {world.lineage.max_generation()}  fingerprint {config.fingerprint()}")


if __name__ == "__main__":
    main()
