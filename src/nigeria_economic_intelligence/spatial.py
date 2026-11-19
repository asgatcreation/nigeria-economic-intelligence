"""Spatial weights and Moran's I.

The report's state findings keep describing a north-south pattern. That
description has so far rested on grouping states by zone and comparing
the groups -- which is to say, on a division drawn before looking at the
data. Moran's I asks the question the other way round: without being
told where north is, do states with similar values sit near each other
more than chance allows?

Two choices have to be declared, because both affect the answer.

*Neighbours.* Contiguity (who shares a border) is the usual choice for
administrative units, but computing it correctly from generalised
polygons is fiddly -- shared borders in a simplified boundary file do
not always share vertices. This module uses k-nearest-neighbours on the
published state centroids instead: unambiguous to compute, symmetric in
coverage (every state has exactly k neighbours, so no state is isolated
and none dominates), and standard practice. Because k is a free
parameter, every result is reported across a range of k rather than at
one flattering value.

*Inference.* The normal approximation for Moran's I is unreliable at
n = 37. The p-values here are permutation-based: the observed statistic
is compared against the distribution produced by shuffling the values
across the same geography, which assumes nothing about their
distribution.

Everything is computed here rather than imported from PySAL so that the
arithmetic is visible and testable; the tests check it against cases
with known answers.
"""

from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

EARTH_RADIUS_KM = 6371.0088
DEFAULT_K = 4
DEFAULT_PERMUTATIONS = 9_999
DEFAULT_SEED = 20261119


def haversine_km(
    first: tuple[float, float],
    second: tuple[float, float],
) -> float:
    """Great-circle distance in kilometres between two (lat, lon) points."""
    lat1, lon1 = math.radians(first[0]), math.radians(first[1])
    lat2, lon2 = math.radians(second[0]), math.radians(second[1])

    dlat = lat2 - lat1
    dlon = lon2 - lon1

    inner = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(inner))


def distance_matrix(points: list[tuple[float, float]]) -> np.ndarray:
    """Pairwise great-circle distances, in kilometres."""
    count = len(points)
    distances = np.zeros((count, count), dtype=float)

    for i in range(count):
        for j in range(i + 1, count):
            separation = haversine_km(points[i], points[j])
            distances[i, j] = separation
            distances[j, i] = separation

    return distances


def knn_weights(
    points: list[tuple[float, float]],
    k: int = DEFAULT_K,
) -> np.ndarray:
    """Row-standardised k-nearest-neighbour spatial weights.

    The matrix is deliberately not symmetrised: if A is one of B's
    nearest neighbours but B is not one of A's, the relation holds one
    way only. Row standardisation then makes each row sum to 1, so
    Moran's I is a correlation between a value and the mean of its
    neighbours.
    """
    count = len(points)
    if count < 2:
        raise ValueError("Spatial weights need at least two points")
    if not 1 <= k <= count - 1:
        raise ValueError(
            f"k must be between 1 and {count - 1} for {count} points, got {k}"
        )

    distances = distance_matrix(points)
    np.fill_diagonal(distances, np.inf)

    weights = np.zeros((count, count), dtype=float)
    for row in range(count):
        nearest = np.argsort(distances[row], kind="stable")[:k]
        weights[row, nearest] = 1.0 / k

    return weights


@dataclass(frozen=True)
class MoranResult:
    """Global Moran's I with permutation inference."""

    i: float
    expected: float
    n: int
    k: int
    permutations: int
    p_value: float
    z_score: float

    @property
    def clustered(self) -> bool:
        """Positive autocorrelation at the conventional 5% threshold."""
        return self.i > self.expected and self.p_value < 0.05


def _statistic(values: np.ndarray, weights: np.ndarray) -> float:
    deviations = values - values.mean()
    denominator = float((deviations**2).sum())

    if denominator == 0:
        raise ValueError("Moran's I is undefined for a constant series")

    total_weight = float(weights.sum())
    numerator = float(deviations @ weights @ deviations)

    return (len(values) / total_weight) * (numerator / denominator)


def morans_i(
    values,
    weights: np.ndarray,
    *,
    permutations: int = DEFAULT_PERMUTATIONS,
    seed: int = DEFAULT_SEED,
    k: int = DEFAULT_K,
) -> MoranResult:
    """Global Moran's I, with a two-sided permutation p-value.

    The p-value is the proportion of random re-allocations of the same
    values across the same geography that produce a statistic at least
    as extreme as the observed one, counting the observed value itself
    so that it can never be reported as zero.
    """
    series = np.asarray(values, dtype=float)

    if series.ndim != 1:
        raise ValueError("Moran's I takes a one-dimensional series")
    if len(series) != weights.shape[0]:
        raise ValueError(
            f"{len(series)} values against a "
            f"{weights.shape[0]}-row weights matrix"
        )
    if np.isnan(series).any():
        raise ValueError("Moran's I cannot be computed with missing values")

    observed = _statistic(series, weights)
    expected = -1.0 / (len(series) - 1)

    generator = np.random.default_rng(seed)
    simulated = np.empty(permutations, dtype=float)
    shuffled = series.copy()

    for index in range(permutations):
        generator.shuffle(shuffled)
        simulated[index] = _statistic(shuffled, weights)

    extreme = int(
        (np.abs(simulated - expected) >= abs(observed - expected)).sum()
    )
    p_value = (extreme + 1) / (permutations + 1)

    spread = simulated.std(ddof=1)
    z_score = (observed - expected) / spread if spread > 0 else math.nan

    return MoranResult(
        i=float(observed),
        expected=float(expected),
        n=len(series),
        k=k,
        permutations=permutations,
        p_value=float(p_value),
        z_score=float(z_score),
    )


def moran_across_k(
    values,
    points: list[tuple[float, float]],
    neighbours=(3, 4, 5, 6, 8),
    *,
    permutations: int = DEFAULT_PERMUTATIONS,
    seed: int = DEFAULT_SEED,
) -> list[MoranResult]:
    """Moran's I at several k, because k is a choice and not a finding."""
    return [
        morans_i(
            values,
            knn_weights(points, k),
            permutations=permutations,
            seed=seed,
            k=k,
        )
        for k in neighbours
    ]
