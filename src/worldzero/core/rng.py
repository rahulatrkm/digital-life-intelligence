"""Controlled randomness.

Whitepaper section 11.2 makes three determinism demands:

* every run has an explicit seed;
* randomness comes only from controlled generators;
* parallel execution must not change biological outcomes.

The third is the awkward one. If mutation draws from a single global stream the
result depends on the order in which cells happen to be processed, so sharding a
population across workers would silently change evolution. Every stochastic
decision that belongs to a *cell* therefore draws from a stream derived from
that cell's identity rather than from a shared cursor.
"""

from __future__ import annotations

import hashlib
import random
from collections.abc import Sequence
from typing import Any, TypeVar

T = TypeVar("T")

_MASK64 = (1 << 64) - 1


def derive_seed(root_seed: int, *parts: Any) -> int:
    """Derive a stable 64-bit seed from a root seed and any hashable parts.

    Uses blake2b rather than :func:`hash` because Python's string hashing is
    randomised per process, which would make runs irreproducible across
    invocations.
    """
    digest = hashlib.blake2b(digest_size=8)
    digest.update(str(int(root_seed) & _MASK64).encode("utf-8"))
    for part in parts:
        digest.update(b"\x1f")
        digest.update(str(part).encode("utf-8"))
    return int.from_bytes(digest.digest(), "big")


class DeterministicRNG:
    """A named collection of independent, reproducible random streams."""

    __slots__ = ("_root_seed", "_streams")

    def __init__(self, seed: int) -> None:
        self._root_seed = int(seed) & _MASK64
        self._streams: dict[str, random.Random] = {}

    @property
    def seed(self) -> int:
        return self._root_seed

    def stream(self, name: str) -> random.Random:
        """Return the persistent stream called *name*, creating it if needed."""
        stream = self._streams.get(name)
        if stream is None:
            stream = random.Random(derive_seed(self._root_seed, "stream", name))
            self._streams[name] = stream
        return stream

    def local(self, *parts: Any) -> random.Random:
        """Return a throwaway stream keyed by *parts*.

        Order-independent: two runs that process the same cell at the same
        timestep get the same draws regardless of scheduling.
        """
        return random.Random(derive_seed(self._root_seed, *parts))

    # -- convenience wrappers -------------------------------------------------

    def random(self, stream: str = "default") -> float:
        return self.stream(stream).random()

    def randint(self, low: int, high: int, stream: str = "default") -> int:
        """Inclusive on both ends, matching :meth:`random.Random.randint`."""
        return self.stream(stream).randint(low, high)

    def uniform(self, low: float, high: float, stream: str = "default") -> float:
        return self.stream(stream).uniform(low, high)

    def gauss(self, mu: float, sigma: float, stream: str = "default") -> float:
        return self.stream(stream).gauss(mu, sigma)

    def choice(self, seq: Sequence[T], stream: str = "default") -> T:
        return self.stream(stream).choice(seq)

    def shuffled(self, seq: Sequence[T], stream: str = "default") -> list[T]:
        items = list(seq)
        self.stream(stream).shuffle(items)
        return items

    def numpy_seed(self, name: str) -> int:
        """A 32-bit seed for numpy generators, which reject 64-bit-negative values."""
        return derive_seed(self._root_seed, "numpy", name) % (2**32)

    # -- checkpointing --------------------------------------------------------

    def state(self) -> dict[str, Any]:
        """Full generator state for a checkpoint.

        Re-seeding from the root alone is not enough: persistent streams such as
        ``schedule`` and ``ids`` have advanced, so a world restored without their
        internal state resumes on a different draw sequence and diverges from the
        run it was supposed to continue.
        """
        streams = {}
        for name, stream in self._streams.items():
            version, internal, gauss = stream.getstate()
            streams[name] = {"version": version, "internal": list(internal), "gauss": gauss}
        return {"root_seed": self._root_seed, "streams": streams}

    def load_state(self, data: dict[str, Any]) -> None:
        if not data:
            return
        self._root_seed = int(data.get("root_seed", self._root_seed)) & _MASK64
        self._streams = {}
        for name, blob in (data.get("streams") or {}).items():
            stream = random.Random()
            # JSON restores the internal state as a list; setstate demands a tuple.
            stream.setstate((blob["version"], tuple(blob["internal"]), blob["gauss"]))
            self._streams[name] = stream

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"DeterministicRNG(seed={self._root_seed}, streams={sorted(self._streams)})"
