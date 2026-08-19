"""Information-theoretic and non-parametric statistics.

Deliberately dependency-light (numpy only). The detectors in section 14 need
effect sizes with uncertainty attached, not point estimates, because section
15.3 asks us to distinguish real adaptive mechanism from noise. Permutation
tests are used in preference to parametric ones: none of these quantities are
normally distributed and sample sizes vary wildly between runs.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import comb

import numpy as np


@dataclass(slots=True)
class TestResult:
    statistic: float
    p_value: float
    effect_size: float
    n_treatment: int
    n_control: int
    resolution: float = 0.0
    """Smallest p-value the design can produce at this sample size.

    A permutation test cannot report a p below 1/(number of distinct labellings),
    so at 3 versus 3 runs a two-sided test bottoms out near 0.10 no matter how
    large the effect. Without this, an underpowered comparison is indistinguishable
    from a real null."""

    @property
    def significant(self) -> bool:
        return self.p_value < 0.05

    @property
    def underpowered(self) -> bool:
        """True when significance is unreachable regardless of effect size."""
        return self.resolution > 0.05

    def to_dict(self) -> dict[str, float | int | bool]:
        return {
            "statistic": round(self.statistic, 6),
            "p_value": round(self.p_value, 6),
            "effect_size": round(self.effect_size, 6),
            "n_treatment": self.n_treatment,
            "n_control": self.n_control,
            "resolution": round(self.resolution, 6),
            "significant": self.significant,
            "underpowered": self.underpowered,
        }


def discretise(values: np.ndarray, bins: int = 8) -> np.ndarray:
    """Quantile-bin a continuous variable.

    Equal-width bins are useless here: resource values are heavily
    zero-inflated, so almost everything lands in bin 0 and the mutual
    information collapses to zero regardless of the underlying relationship.
    """
    values = np.asarray(values, dtype=np.float64).ravel()
    if values.size == 0:
        return np.zeros(0, dtype=np.int64)
    unique = np.unique(values)
    if unique.size <= bins:
        return np.searchsorted(unique, values)
    edges = np.quantile(values, np.linspace(0.0, 1.0, bins + 1)[1:-1])
    return np.searchsorted(edges, values)


def entropy(labels: np.ndarray) -> float:
    labels = np.asarray(labels).ravel()
    if labels.size == 0:
        return 0.0
    _, counts = np.unique(labels, return_counts=True)
    probabilities = counts / counts.sum()
    return float(-np.sum(probabilities * np.log2(probabilities)))


def mutual_information(x: np.ndarray, y: np.ndarray, bins: int = 8) -> float:
    """Discrete mutual information I(X;Y) in bits."""
    x = np.asarray(x).ravel()
    y = np.asarray(y).ravel()
    if x.size == 0 or x.size != y.size:
        return 0.0
    xd = discretise(x, bins) if not np.issubdtype(x.dtype, np.integer) else x
    yd = discretise(y, bins) if not np.issubdtype(y.dtype, np.integer) else y

    x_values, x_index = np.unique(xd, return_inverse=True)
    y_values, y_index = np.unique(yd, return_inverse=True)
    if x_values.size < 2 or y_values.size < 2:
        return 0.0

    joint = np.zeros((x_values.size, y_values.size), dtype=np.float64)
    np.add.at(joint, (x_index, y_index), 1.0)
    joint /= joint.sum()

    px = joint.sum(axis=1, keepdims=True)
    py = joint.sum(axis=0, keepdims=True)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = joint / (px * py)
        terms = joint * np.log2(ratio)
    return float(np.nansum(np.where(joint > 0, terms, 0.0)))


def normalised_mutual_information(x: np.ndarray, y: np.ndarray, bins: int = 8) -> float:
    """MI scaled into [0, 1] by the smaller marginal entropy.

    Raw MI is unbounded above and scales with the number of occupied bins, so
    comparing it across runs with different population sizes is meaningless.
    """
    mi = mutual_information(x, y, bins)
    if mi <= 0.0:
        return 0.0
    xd = discretise(np.asarray(x), bins)
    yd = discretise(np.asarray(y), bins)
    denominator = min(entropy(xd), entropy(yd))
    return float(mi / denominator) if denominator > 0 else 0.0


def permutation_test(
    treatment: np.ndarray,
    control: np.ndarray,
    *,
    iterations: int = 2000,
    seed: int = 0,
    alternative: str = "greater",
) -> TestResult:
    """Difference-of-means test by label shuffling.

    ``alternative='greater'`` is the default because every control in section 17
    *removes* a mechanism, so the prediction is directional: the treatment should
    beat the control, not merely differ from it. A two-sided test spends half its
    power on an outcome the design excludes, which at small seed counts is the
    difference between a detectable effect and an undetectable one.

    Enumerates every labelling when there are few enough to do so, which removes
    Monte Carlo noise from exactly the small-sample case where it matters most.
    """
    treatment = np.asarray(treatment, dtype=np.float64).ravel()
    control = np.asarray(control, dtype=np.float64).ravel()
    if treatment.size == 0 or control.size == 0:
        return TestResult(0.0, 1.0, 0.0, treatment.size, control.size, 1.0)

    observed = float(treatment.mean() - control.mean())
    combined = np.concatenate([treatment, control])
    split = treatment.size
    total = combined.size
    two_sided = alternative == "two-sided"

    def qualifies(difference: float) -> bool:
        return abs(difference) >= abs(observed) if two_sided else difference >= observed

    labellings = comb(total, split)
    if labellings <= iterations:
        count = 0
        for subset in combinations(range(total), split):
            mask = np.zeros(total, dtype=bool)
            mask[list(subset)] = True
            if qualifies(float(combined[mask].mean() - combined[~mask].mean())):
                count += 1
        p_value = count / labellings
        # The observed labelling always qualifies, and under a two-sided rule its
        # mirror does too, so those set the floor.
        resolution = (2.0 if two_sided else 1.0) / labellings
    else:
        generator = np.random.default_rng(seed)
        shuffled = combined.copy()
        count = 0
        for _ in range(iterations):
            generator.shuffle(shuffled)
            if qualifies(float(shuffled[:split].mean() - shuffled[split:].mean())):
                count += 1
        p_value = (count + 1) / (iterations + 1)
        resolution = 1.0 / (iterations + 1)

    return TestResult(
        statistic=observed,
        p_value=p_value,
        effect_size=cohens_d(treatment, control),
        n_treatment=treatment.size,
        n_control=control.size,
        resolution=resolution,
    )


def cohens_d(treatment: np.ndarray, control: np.ndarray) -> float:
    treatment = np.asarray(treatment, dtype=np.float64).ravel()
    control = np.asarray(control, dtype=np.float64).ravel()
    if treatment.size < 2 or control.size < 2:
        return 0.0
    nt, nc = treatment.size, control.size
    pooled = ((nt - 1) * treatment.var(ddof=1) + (nc - 1) * control.var(ddof=1)) / (nt + nc - 2)
    if pooled <= 0:
        return 0.0
    return float((treatment.mean() - control.mean()) / np.sqrt(pooled))


def bootstrap_ci(
    values: np.ndarray,
    *,
    iterations: int = 2000,
    alpha: float = 0.05,
    seed: int = 0,
) -> tuple[float, float]:
    values = np.asarray(values, dtype=np.float64).ravel()
    if values.size == 0:
        return (0.0, 0.0)
    generator = np.random.default_rng(seed)
    samples = generator.choice(values, size=(iterations, values.size), replace=True).mean(axis=1)
    low = float(np.quantile(samples, alpha / 2))
    high = float(np.quantile(samples, 1 - alpha / 2))
    return (low, high)


def lagged_mutual_information(
    actions: np.ndarray,
    future_state: np.ndarray,
    lag: int,
    bins: int = 8,
) -> float:
    """I(action_t ; state_{t+lag}) -- the prediction detector's core quantity."""
    actions = np.asarray(actions).ravel()
    future_state = np.asarray(future_state).ravel()
    if lag <= 0 or actions.size <= lag:
        return 0.0
    return normalised_mutual_information(actions[:-lag], future_state[lag:], bins)
