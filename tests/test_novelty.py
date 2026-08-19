"""The novelty archive's persistence filter.

Section 15.2 wants transient mutants excluded and genuinely persistent
behaviours archived. The original filter keyed candidates on a hash of the
signature, but the signature is a continuous population average, so two
near-identical behaviours hashed differently, no candidate ever recurred, and
the archive stayed empty for the whole run. `novelty_archive` was then a
constant zero, which silently forced the stage 9 and 10 criteria that read it
to fail regardless of what evolved.
"""

from __future__ import annotations

import numpy as np

from worldzero.metrics.novelty import NoveltyArchive


def signature(*values: float) -> np.ndarray:
    return np.asarray(values, dtype=np.float64)


def test_recurring_behaviour_is_archived() -> None:
    archive = NoveltyArchive(threshold=0.15, min_generations=3)
    behaviour = signature(1.0, 0.0, 0.0)

    for generation in (1, 2, 3):
        archive.observe(behaviour, generation)

    assert len(archive.archive) == 1
    assert archive.accepted == 1


def test_near_identical_signatures_count_as_the_same_candidate() -> None:
    """The regression: drift far below the novelty threshold must not create a
    brand new candidate each time."""
    archive = NoveltyArchive(threshold=0.15, min_generations=3)

    for generation, jitter in enumerate((0.0, 0.01, 0.02), start=1):
        archive.observe(signature(1.0 + jitter, 0.0, 0.0), generation)

    assert len(archive.archive) == 1, "drifting signature never accumulated generations"


def test_one_generation_wonder_is_not_archived() -> None:
    archive = NoveltyArchive(threshold=0.15, min_generations=3)

    archive.observe(signature(1.0, 0.0, 0.0), 1)
    archive.observe(signature(1.0, 0.0, 0.0), 1)

    assert archive.archive == []
    assert len(archive.pending) == 1


def test_distinct_behaviours_stay_distinct() -> None:
    archive = NoveltyArchive(threshold=0.15, min_generations=2)

    for generation in (1, 2):
        archive.observe(signature(1.0, 0.0, 0.0), generation)
        archive.observe(signature(0.0, 1.0, 0.0), generation)

    assert len(archive.archive) == 2


def test_transient_candidates_are_pruned() -> None:
    archive = NoveltyArchive(threshold=0.15, min_generations=3)
    archive.observe(signature(1.0, 0.0, 0.0), 1)

    archive.prune(current_generation=100, window=20)

    assert archive.pending == []
    assert archive.rejected_transient == 1


def test_archived_behaviour_is_no_longer_novel() -> None:
    archive = NoveltyArchive(threshold=0.15, min_generations=2)
    behaviour = signature(1.0, 0.0, 0.0)

    for generation in (1, 2):
        archive.observe(behaviour, generation)

    assert archive.distance(behaviour) == 0.0
    assert archive.observe(behaviour, 3) < archive.threshold
    assert len(archive.archive) == 1, "an archived behaviour must not be re-archived"


def test_archive_grows_over_a_real_run() -> None:
    """End to end: a live world must produce a non-empty archive."""
    from worldzero.core.config import SimulationConfig
    from worldzero.core.world import World
    from worldzero.metrics.core import MetricEngine

    config = SimulationConfig(name="novelty").merged(
        {
            "world": {"width": 32, "height": 32, "seed": 3},
            "cell": {"start_population": 80, "max_sensor_stage": 2},
            "resources": {"regime": "regenerating", "initial_density": 0.16, "regen_rate": 0.1},
            "hazards": {"regime": "static"},
            "logging": {"metrics_interval": 50},
            "stop": {"max_steps": 1500},
        }
    )
    world = World(config)
    metrics = MetricEngine()

    for _ in range(1500):
        world.step()
        if not world.cells:
            break
        if world.timestep % 50 == 0:
            metrics.compute(world, None)

    series = [row["novelty_archive"] for row in metrics.to_rows() if "novelty_archive" in row]

    assert series, "no novelty metric recorded"
    assert max(series) > 0, "archive stayed empty for the whole run"
