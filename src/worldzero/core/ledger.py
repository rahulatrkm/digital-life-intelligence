"""Energy bookkeeping.

Whitepaper section 21 asks for "all costs and gains balance within expected
tolerance". Without a ledger that is unfalsifiable, so every joule that enters
or leaves the population is attributed to a bucket and the invariant

    injected == in_living_cells + spent + lost_at_death - initial_endowment

is checked directly in the test suite.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass
class EnergyLedger:
    initial_endowment: float = 0.0
    harvested: float = 0.0
    spent_moving: float = 0.0
    spent_idle: float = 0.0
    spent_sensing: float = 0.0
    spent_signalling: float = 0.0
    spent_memory: float = 0.0
    spent_probing: float = 0.0
    spent_altering: float = 0.0
    spent_consuming: float = 0.0
    spent_reproducing: float = 0.0
    lost_at_death: float = 0.0
    lost_to_cap: float = 0.0
    """Energy discarded when a cell would exceed ``max_energy``; tracked so the
    cap cannot silently hide a resource-accounting bug."""

    @property
    def spent(self) -> float:
        return (
            self.spent_moving
            + self.spent_idle
            + self.spent_sensing
            + self.spent_signalling
            + self.spent_memory
            + self.spent_probing
            + self.spent_altering
            + self.spent_consuming
            + self.spent_reproducing
        )

    def balance(self, living_energy: float) -> float:
        """Residual of the conservation identity; should sit at ~0."""
        expected = self.initial_endowment + self.harvested
        accounted = living_energy + self.spent + self.lost_at_death + self.lost_to_cap
        return expected - accounted

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["spent_total"] = self.spent
        return data

    def load(self, data: dict[str, Any]) -> None:
        for key, value in data.items():
            if key != "spent_total" and hasattr(self, key):
                setattr(self, key, float(value))
