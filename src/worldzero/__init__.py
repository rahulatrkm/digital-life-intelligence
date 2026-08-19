"""World Zero: a buildable digital-life simulator.

Reference implementation of *The Origin of Machine Intelligence: A Digital Life
Theory of Emergent Intelligence and a Practical Blueprint to Build the
Simulator* (v4, August 2026).

The package intentionally contains no pretrained model, no planner, no explicit
reward function and no designed language. Cells are engineered to live, mutate,
reproduce and die -- they are not engineered to think (whitepaper section 3).
"""

from __future__ import annotations

__version__ = "0.1.0"

from worldzero.core.config import SimulationConfig
from worldzero.core.types import Action, ActionType, Cell, Direction
from worldzero.core.world import World
from worldzero.genome.gene import Comparator, Gene, Genome, Sensor, WriteExpr

__all__ = [
    "__version__",
    "Action",
    "ActionType",
    "Cell",
    "Comparator",
    "Direction",
    "Gene",
    "Genome",
    "Sensor",
    "SimulationConfig",
    "World",
    "WriteExpr",
]
