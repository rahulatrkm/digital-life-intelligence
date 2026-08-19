"""Baselines and controls (whitepaper section 17).

Every control here *removes* a mechanism. None of them add one, and none change
the resource economy, so a fitness gap between a treatment and its control is
attributable to the missing mechanism rather than to a different world.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ControlSpec:
    name: str
    purpose: str
    overrides: dict[str, Any] = field(default_factory=dict)


CONTROLS: dict[str, ControlSpec] = {
    "random": ControlSpec(
        "random",
        "Establish a non-adaptive baseline",
        {"controls": {"random_actions": True}},
    ),
    "no_mutation": ControlSpec(
        "no_mutation",
        "Show adaptation requires heritable variation",
        {"controls": {"disable_mutation": True}, "mutation": {"enabled": False}},
    ),
    "no_reproduction": ControlSpec(
        "no_reproduction",
        "Show lineage evolution matters",
        {"controls": {"disable_reproduction": True}},
    ),
    "no_memory": ControlSpec(
        "no_memory",
        "Test memory contribution, and act as the reactive baseline for prediction",
        {"controls": {"disable_memory": True}},
    ),
    "scrambled_memory": ControlSpec(
        "scrambled_memory",
        "Test whether memory content matters, holding the architecture fixed",
        {"controls": {"scramble_memory": True}},
    ),
    "scrambled_signals": ControlSpec(
        "scrambled_signals",
        "Test whether signals carry meaning rather than merely existing",
        {"controls": {"scramble_signals": True}},
    ),
    "isolated": ControlSpec(
        "isolated",
        "Test cooperation versus individual action",
        {"controls": {"isolate_cells": True}},
    ),
    "static_env": ControlSpec(
        "static_env",
        "Test whether environmental change is needed for higher emergence",
        {"controls": {"static_environment": True}},
    ),
    "no_markers": ControlSpec(
        "no_markers",
        "Remove the external memory layer that culture is written onto",
        {"controls": {"disable_markers": True}},
    ),
    "no_probe": ControlSpec(
        "no_probe",
        "Remove costly information-gathering intervention",
        {"controls": {"disable_probe": True}},
    ),
    "single_variant": ControlSpec(
        "single_variant",
        "Memorisation baseline: one surface signature, nothing to abstract over",
        {"resources": {"variants": 1}},
    ),
    "alternative_physics": ControlSpec(
        "alternative_physics",
        "Detect artifacts of one simulator by changing world topology",
        {"world": {"wrap": False}},
    ),
}


def apply_control(config, name: str):
    """Return *config* with the named control's overrides applied."""
    spec = CONTROLS.get(name)
    if spec is None:
        raise ValueError(f"Unknown control '{name}'. Available: {sorted(CONTROLS)}")
    return config.merged(spec.overrides)


def describe_controls() -> list[dict[str, Any]]:
    return [
        {"name": s.name, "purpose": s.purpose, "overrides": s.overrides} for s in CONTROLS.values()
    ]
