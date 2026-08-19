"""Information-theoretic and non-parametric statistics.

Deliberately dependency-light (numpy only). The detectors in section 14 need
effect sizes with uncertainty attached, not point estimates, because section
15.3 asks us to distinguish real adaptive mechanism from noise. Permutation
tests are used in preference to parametric ones: none of these quantities are
normally distributed and sample sizes vary wildly between runs.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(slots=True)
class TestResult:
    statistic: float
    p_value: float
    effect_size: float
    n_treatment: int
    n_control: int

    @property
    def significant(self) -> bool:
        return self.p_value < 0.05

    def to_dict(self) -> dict[str, float | int | bool]:
        return {
            "statistic": round(self.statistic, 6),
            "p_value": round(self.p_value, 6),
            "effect_size": round(self.effect_size, 6),
            "n_treatment": self.n_treatment,
            "n_control": self.n_control,
            "significant": self.significant,
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
) -> TestResult:
    """Two-sided difference-of-means test by label shuffling."""
    treatment = np.asarray(treatment, dtype=np.float64).ravel()
    control = np.asarray(control, dtype=np.float64).ravel()
    if treatment.size == 0 or control.size == 0:
        return TestResult(0.0, 1.0, 0.0, treatment.size, control.size)

    observed = float(treatment.mean() - control.mean())
    combined = np.concatenate([treatment, control])
    split = treatment.size
    generator = np.random.default_rng(seed)

    count = 0
    for _ in range(iterations):
        generator.shuffle(combined)
        difference = combined[:split].mean() - combined[split:].mean()
        if abs(difference) >= abs(observed):
            count += 1

    p_value = (count + 1) / (iterations + 1)
    return TestResult(
        statistic=observed,
        p_value=p_value,
        effect_size=cohens_d(treatment, control),
        n_treatment=treatment.size,
        n_control=control.size,
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
