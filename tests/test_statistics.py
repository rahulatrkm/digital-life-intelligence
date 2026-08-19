"""Statistical power of the control comparisons.

A permutation test cannot report a p-value below 1/(number of distinct
labellings). At 3 versus 3 runs a two-sided test bottoms out near 0.10, so the
`p < 0.05` criterion was unreachable regardless of effect size and every
control-comparison detector failed by construction. These tests pin the
arithmetic so the default replicate count cannot silently drop below the
resolution of its own test again.
"""

from __future__ import annotations

from math import comb

import numpy as np
import pytest

from worldzero.cli import build_parser
from worldzero.metrics.information import permutation_test

SEPARATED_TREATMENT = np.array([10.0, 11.0, 12.0])
SEPARATED_CONTROL = np.array([1.0, 2.0, 3.0])


def test_three_versus_three_cannot_reach_significance_two_sided() -> None:
    """The original failure: a huge effect still reports p ~ 0.10."""
    result = permutation_test(
        SEPARATED_TREATMENT, SEPARATED_CONTROL, alternative="two-sided"
    )

    assert result.effect_size > 2.0
    assert result.p_value == pytest.approx(2 / comb(6, 3), abs=1e-9)
    assert not result.significant
    assert result.underpowered


def test_directional_test_halves_the_floor() -> None:
    result = permutation_test(SEPARATED_TREATMENT, SEPARATED_CONTROL, alternative="greater")

    assert result.p_value == pytest.approx(1 / comb(6, 3), abs=1e-9)
    assert result.resolution == pytest.approx(1 / comb(6, 3), abs=1e-9)


def test_five_versus_five_has_resolution_to_detect() -> None:
    treatment = np.array([10.0, 11.0, 12.0, 13.0, 14.0])
    control = np.array([1.0, 2.0, 3.0, 4.0, 5.0])

    result = permutation_test(treatment, control)

    assert result.resolution == pytest.approx(1 / comb(10, 5), abs=1e-9)
    assert not result.underpowered
    assert result.significant


def test_small_samples_are_enumerated_exactly() -> None:
    """Exact enumeration removes Monte Carlo noise where it matters most."""
    a = permutation_test(SEPARATED_TREATMENT, SEPARATED_CONTROL, seed=1)
    b = permutation_test(SEPARATED_TREATMENT, SEPARATED_CONTROL, seed=999)

    assert a.p_value == b.p_value


def test_identical_arms_are_not_significant() -> None:
    values = np.array([5.0, 5.0, 5.0, 5.0, 5.0])
    result = permutation_test(values, values.copy())

    assert not result.significant
    assert result.statistic == pytest.approx(0.0)


def test_control_beating_treatment_is_not_significant() -> None:
    result = permutation_test(SEPARATED_CONTROL, SEPARATED_TREATMENT)

    assert result.statistic < 0
    assert not result.significant


def test_empty_arm_is_reported_as_no_resolution() -> None:
    result = permutation_test(np.array([]), SEPARATED_CONTROL)

    assert result.p_value == 1.0
    assert result.underpowered


@pytest.mark.parametrize("command", ["experiment", "suite"])
def test_cli_defaults_to_a_powered_replicate_count(command: str) -> None:
    argv = [command, "E0"] if command == "experiment" else [command]
    args = build_parser().parse_args(argv)

    assert args.replicates >= 5
    # The default must be able to clear p < 0.05 on a clean separation.
    assert 1 / comb(2 * args.replicates, args.replicates) < 0.05
