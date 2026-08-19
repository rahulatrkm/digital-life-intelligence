"""Terminal visualisation and replay (whitepaper section 11, 'Visualization UI').

Text rendering rather than a GUI so a run can be inspected over SSH and pasted
into a bug report. Matplotlib is optional and only used for the metric
dashboard.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np

if TYPE_CHECKING:  # pragma: no cover
    from worldzero.core.world import World

CELL_GLYPH = "@"
RESOURCE_RAMP = " .:-=+*#%"
HAZARD_GLYPH = "x"
MARKER_GLYPH = "'"
OBSTACLE_GLYPH = "#"


def render_world(world: World, *, max_width: int = 120, max_height: int = 48) -> str:
    """One frame of the grid, downsampled to fit a terminal.

    Cells are drawn last and unconditionally: population is the thing you are
    usually looking for, and at any real density it would otherwise be hidden
    under the resource ramp.
    """
    step_x = max(1, world.width // max_width)
    step_y = max(1, world.height // max_height)

    resource = world.resource[::step_y, ::step_x]
    hazard = world.hazard[::step_y, ::step_x]
    marker = world.marker[::step_y, ::step_x]
    obstacle = world.obstacle[::step_y, ::step_x]
    peak = float(resource.max()) or 1.0

    rows = []
    for y in range(resource.shape[0]):
        row = []
        for x in range(resource.shape[1]):
            if obstacle[y, x]:
                row.append(OBSTACLE_GLYPH)
            elif hazard[y, x] > 0.0:
                row.append(HAZARD_GLYPH)
            elif marker[y, x] > 0.01:
                row.append(MARKER_GLYPH)
            else:
                level = int((resource[y, x] / peak) * (len(RESOURCE_RAMP) - 1))
                row.append(RESOURCE_RAMP[max(0, min(len(RESOURCE_RAMP) - 1, level))])
        rows.append(row)

    for x, y in world.occupancy:
        gy, gx = y // step_y, x // step_x
        if 0 <= gy < len(rows) and 0 <= gx < len(rows[0]):
            rows[gy][gx] = CELL_GLYPH

    header = (
        f"t={world.timestep}  pop={world.population}  "
        f"births={world.births}  deaths={world.deaths}  "
        f"gen={world.lineage.max_generation()}"
    )
    body = "\n".join("".join(row) for row in rows)
    legend = (
        f"  {CELL_GLYPH} cell   {HAZARD_GLYPH} hazard   "
        f"{MARKER_GLYPH} marker   [{RESOURCE_RAMP}] resource"
    )
    return f"{header}\n{body}\n{legend}"


def render_metrics(series: list[dict[str, Any]], keys: tuple[str, ...], width: int = 60) -> str:
    """Sparkline-style summary of selected metric series."""
    ramp = "_.-~^"
    lines = []
    for key in keys:
        values = [float(row[key]) for row in series if key in row]
        if not values:
            continue
        array = np.asarray(values, dtype=np.float64)
        if array.size > width:
            # Bucket-average rather than stride-sample so a spike between two
            # sampled indices is not silently dropped from the picture.
            buckets = np.array_split(array, width)
            array = np.asarray([b.mean() for b in buckets])
        low, high = float(array.min()), float(array.max())
        span = (high - low) or 1.0
        spark = "".join(ramp[int((v - low) / span * (len(ramp) - 1))] for v in array)
        lines.append(f"{key:>22} |{spark}| {low:.3g} .. {high:.3g}")
    return "\n".join(lines)


def plot_metrics(series: list[dict[str, Any]], keys: tuple[str, ...], path: str | Path) -> bool:
    """Write a PNG dashboard. Returns False when matplotlib is not installed."""
    try:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return False

    present = [k for k in keys if any(k in row for row in series)]
    if not present:
        return False

    steps = [row["timestep"] for row in series]
    fig, axes = plt.subplots(len(present), 1, figsize=(10, 2.2 * len(present)), sharex=True)
    if len(present) == 1:
        axes = [axes]
    for axis, key in zip(axes, present, strict=False):
        axis.plot(steps, [row.get(key, float("nan")) for row in series], linewidth=1.2)
        axis.set_ylabel(key, fontsize=8)
        axis.grid(alpha=0.3)
    axes[-1].set_xlabel("timestep")
    fig.tight_layout()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return True


def replay_summary(events_path: str | Path, *, limit: int = 0) -> dict[str, Any]:
    """Aggregate an event log without loading it all into memory."""
    from worldzero.storage.events import read_events

    counts: dict[str, int] = {}
    first_detections: list[dict[str, Any]] = []
    extinction: int | None = None
    last_step = 0

    for index, event in enumerate(read_events(events_path)):
        if limit and index >= limit:
            break
        key = event.event_type.value
        counts[key] = counts.get(key, 0) + 1
        last_step = max(last_step, event.timestep)
        if key == "FIRST_DETECTION":
            first_detections.append({"timestep": event.timestep, **event.payload})
        elif key == "EXTINCTION":
            extinction = event.timestep

    return {
        "events": sum(counts.values()),
        "counts": counts,
        "last_timestep": last_step,
        "first_detections": first_detections,
        "extinction": extinction,
    }
