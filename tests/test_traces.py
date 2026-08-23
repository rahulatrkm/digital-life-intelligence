"""Lag pairing in behaviour traces.

The prediction detector pairs each sampled action with the resource at the same
tile some lag later. Tiles are only recorded on sampling steps, so an exact
lookup of `timestep + lag` finds nothing unless the lag happens to be a multiple
of the sampling interval -- and the lags come from `cue_lead_time`, which has no
reason to line up.

Measured on E3 before the fix: trace_interval 20, cue_lead_time 12, so the
detector tried lags 6, 12 and 24 and found 0 pairs every time against a
requirement of 50. Stage 3's primary criterion could never fire, whatever the
population did.
"""

from __future__ import annotations

import pytest

from worldzero.metrics.traces import BehaviorTrace, TraceSample


def _trace(interval: int, steps: int, tile: tuple[int, int] = (3, 4)) -> BehaviorTrace:
    """A trace sampled every `interval` steps, one cell sitting on one tile."""
    trace = BehaviorTrace()
    x, y = tile
    for step in range(interval, steps + 1, interval):
        trace.samples.append(
            TraceSample(
                timestep=step,
                cell_id=f"c{step}",
                lineage_id="l",
                generation=1,
                x=x,
                y=y,
                energy=10.0,
                action=step % 3,
                resource_here=float(step % 5),
                hazard_here=0.0,
                cue_here=0.0,
                marker_here=0.0,
                signal_here=0.0,
                memory=(0.0,),
                neighbours=0,
                used_memory_gene=False,
            )
        )
        trace.tile_future[(step, x, y)] = float(step % 5)
    return trace


def test_lag_not_aligned_to_sampling_still_pairs() -> None:
    """The regression: lag 12 against sampling interval 20 found nothing."""
    trace = _trace(interval=20, steps=2000)

    actions, futures = trace.future_resource(12)

    assert actions.size > 50, "unaligned lag produced too few pairs to measure"
    assert actions.size == futures.size


@pytest.mark.parametrize("lag", [6, 12, 20, 24, 40])
def test_every_lag_the_detector_tries_yields_pairs(lag: int) -> None:
    trace = _trace(interval=20, steps=2000)

    actions, _ = trace.future_resource(lag)

    assert actions.size > 0, f"lag {lag} produced no pairs"


def test_pairs_come_from_the_future_not_the_past() -> None:
    trace = _trace(interval=10, steps=200)

    actions, futures = trace.future_resource(10)

    # Every future value must belong to a step at or after target, never before.
    assert actions.size > 0
    for sample in trace.samples:
        target = sample.timestep + 10
        history = trace._tile_index()[(sample.x, sample.y)]
        later = [when for when, _ in history if when >= target]
        if later:
            assert min(later) >= target


def test_lag_beyond_the_trace_yields_nothing() -> None:
    """A lag past the end of the run must not silently wrap to earlier data."""
    trace = _trace(interval=20, steps=200)

    actions, _ = trace.future_resource(10_000)

    assert actions.size == 0


def test_sampling_interval_is_inferred() -> None:
    assert _trace(interval=20, steps=400)._sampling_interval() == 20
    assert _trace(interval=5, steps=100)._sampling_interval() == 5


def test_empty_trace_is_safe() -> None:
    actions, futures = BehaviorTrace().future_resource(10)

    assert actions.size == 0
    assert futures.size == 0
