"""Fixed workload for comparing simulation speed across code versions.

Single-threaded and deterministic, so two runs differ only by the code under
test. Reports ms/step and the final stats, because a speedup that changes the
result is not a speedup.
"""

from __future__ import annotations

import json
import time

from worldzero.experiments.suite import get_experiment
from worldzero.core.world import World

STEPS = 800


def main() -> None:
    config = get_experiment("E2").build_config(
        {"world": {"width": 64, "height": 64}, "cell": {"start_population": 200}}
    ).with_seed(1)

    world = World(config)
    started = time.perf_counter()
    for _ in range(STEPS):
        world.step()
        if not world.cells:
            break
    elapsed = time.perf_counter() - started

    stats = world.stats()
    print(
        json.dumps(
            {
                "steps": world.timestep,
                "seconds": round(elapsed, 2),
                "ms_per_step": round(1000 * elapsed / max(1, world.timestep), 3),
                "population": stats["population"],
                "births": stats["births"],
                "max_generation": stats["max_generation"],
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
