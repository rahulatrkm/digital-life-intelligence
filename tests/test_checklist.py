"""Whitepaper section 21 implementation checklist.

Covers the rows that are machine-checkable: reproducibility, energy accounting,
lineage tracking, event logging, and exact-vs-accelerated validation.
"""

from __future__ import annotations

from worldzero.core.acceleration import validate_against_exact
from worldzero.core.config import SimulationConfig
from worldzero.core.world import World
from worldzero.storage.checkpoints import load_checkpoint, save_checkpoint
from worldzero.storage.events import EventLog, EventType, read_events

TOLERANCE = 1e-6


def test_energy_accounting_balances(world: World) -> None:
    """injected == in_living_cells + spent + lost_at_death - initial_endowment."""
    for _ in range(200):
        world.step()

    residual = world.ledger.balance(world.living_energy())
    assert abs(residual) < TOLERANCE, f"energy ledger drifted by {residual}"


def test_energy_accounting_balances_through_extinction(config: SimulationConfig) -> None:
    starving = config.merged(
        {
            "resources": {"initial_density": 0.0, "regen_rate": 0.0},
            "cell": {"start_energy": 5.0},
            "stop": {"stop_on_extinction": False},
        }
    )
    world = World(starving)
    for _ in range(300):
        world.step()

    assert world.population == 0
    assert abs(world.ledger.balance(world.living_energy())) < TOLERANCE


def test_energy_never_silently_appears(world: World) -> None:
    for _ in range(100):
        world.step()

    ledger = world.ledger
    assert ledger.harvested >= 0.0
    assert ledger.spent >= 0.0
    assert ledger.initial_endowment > 0.0


def test_same_config_and_seed_produce_identical_stats(config: SimulationConfig) -> None:
    def run() -> dict:
        world = World(config)
        for _ in range(150):
            world.step()
        return world.stats()

    assert run() == run()


def test_config_fingerprint_is_stable_and_sensitive(config: SimulationConfig) -> None:
    assert config.fingerprint() == config.merged({}).fingerprint()
    assert config.fingerprint() != config.with_seed(config.world.seed + 1).fingerprint()


def test_checkpoint_round_trips(world: World, tmp_path) -> None:
    for _ in range(80):
        world.step()

    path = save_checkpoint(world, tmp_path / "ckpt.json")
    restored = load_checkpoint(path)

    assert restored.timestep == world.timestep
    assert restored.population == world.population
    assert restored.births == world.births
    assert restored.deaths == world.deaths
    assert restored.stats() == world.stats()


def test_restored_checkpoint_continues_identically(world: World, tmp_path) -> None:
    for _ in range(60):
        world.step()

    restored = load_checkpoint(save_checkpoint(world, tmp_path / "ckpt.json"))
    for _ in range(40):
        world.step()
        restored.step()

    assert restored.stats() == world.stats()


def test_event_log_records_births_and_deaths(config: SimulationConfig, tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    log = EventLog(path, run_id="r", world_id="w", flush_interval=1)
    world = World(config, run_id="r", world_id="w", event_log=log)
    for _ in range(150):
        world.step()
    log.close()

    events = list(read_events(path))
    kinds = {e.event_type for e in events}

    assert EventType.RUN_START in kinds
    assert EventType.BIRTH in kinds or EventType.DEATH in kinds
    assert all(e.run_id == "r" and e.world_id == "w" for e in events)
    assert all(e.timestep >= 0 for e in events)


def test_accelerated_run_matches_exact_run(config: SimulationConfig) -> None:
    """Section 10.3: accelerated results must be re-checkable against exact ones."""
    accelerated = config.merged({"acceleration": {"enabled": True, "stability_window": 20}})
    report = validate_against_exact(accelerated, steps=200)

    # Section 19 treats a fast/exact gap as the "acceleration artifact" failure.
    # Skipping only fires on a quiescent window, so the gap should be tiny.
    assert report["population_divergence"] <= 0.05
    births = max(1.0, report["exact_births"])
    assert abs(report["exact_births"] - report["accelerated_births"]) / births <= 0.05
