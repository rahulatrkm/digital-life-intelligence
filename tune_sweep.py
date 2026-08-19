"""Throwaway viability sweep. Not part of the package."""
import itertools
import sys

sys.path.insert(0, "src")

from worldzero.core.config import SimulationConfig
from worldzero.core.world import World


def trial(**over):
    c = SimulationConfig()
    c.world.width = c.world.height = 96
    c.cell.start_population = 300
    c.cell.max_sensor_stage = 0
    for k, v in over.items():
        head, tail = k.split(".")
        setattr(getattr(c, head), tail, v)
    w = World(c)
    hist = []
    for i in range(3000):
        w.step()
        if not w.cells:
            break
        if i % 500 == 0:
            hist.append(w.population)
    hist.append(w.population)
    return hist, w.lineage.max_generation()


grid = {
    "resources.initial_density": [0.08, 0.20],
    "resources.regen_rate": [0.01, 0.05],
    "physics.sense_cost": [0.05, 0.02],
    "cell.start_energy": [50.0, 80.0],
}

keys = list(grid)
for combo in itertools.product(*(grid[k] for k in keys)):
    over = dict(zip(keys, combo, strict=True))
    hist, gen = trial(**over)
    print({k.split(".")[1]: v for k, v in over.items()}, "->", hist, "gen", gen, flush=True)
