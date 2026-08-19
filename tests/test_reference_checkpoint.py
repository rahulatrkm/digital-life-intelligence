"""The reference checkpoint committed to the repository.

Regenerate with `python scripts/make_reference_checkpoint.py`.

This is the format's compatibility contract: if a change to the checkpoint
schema stops the shipped file loading, that breaks every checkpoint anyone
already has, and it should fail here rather than in their run.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from worldzero.storage.checkpoints import load_checkpoint, save_checkpoint

REFERENCE = Path(__file__).resolve().parents[1] / "reference" / "world_zero_step2000.json.gz"

pytestmark = pytest.mark.skipif(not REFERENCE.exists(), reason="reference checkpoint not present")


def test_reference_checkpoint_loads() -> None:
    world = load_checkpoint(REFERENCE)

    assert world.timestep == 2000
    assert world.population > 0
    assert world.lineage.max_generation() > 0
    assert not world.lineage.has_orphans()


def test_reference_checkpoint_is_small_enough_for_git() -> None:
    """Guards against someone regenerating it at full scale: a 64x64 world is
    ~250K gzipped and a run directory is far larger."""
    assert REFERENCE.stat().st_size < 512 * 1024


def test_reference_checkpoint_carries_counters_and_rng() -> None:
    world = load_checkpoint(REFERENCE)

    assert world.births > 0
    assert world.deaths > 0

    ledger = world.ledger
    throughput = ledger.initial_endowment + ledger.harvested
    assert abs(ledger.balance(world.living_energy())) < 1e-9 * throughput


def test_reference_checkpoint_resumes_deterministically() -> None:
    first = load_checkpoint(REFERENCE)
    second = load_checkpoint(REFERENCE)

    for _ in range(50):
        first.step()
        second.step()

    assert first.stats() == second.stats()


def test_reference_checkpoint_round_trips_again(tmp_path) -> None:
    world = load_checkpoint(REFERENCE)
    for _ in range(25):
        world.step()

    resaved = load_checkpoint(save_checkpoint(world, tmp_path / "again.json.gz"))

    assert resaved.stats() == world.stats()
