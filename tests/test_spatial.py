"""Tests for the spatial weights and Moran's I implementation.

Moran's I is written out here rather than imported from PySAL, so it has
to be checked against cases whose answers are known independently of the
code: a perfectly segregated grid, a perfectly alternating one, and a
value computed by hand on a four-point layout.
"""

import math

import numpy as np
import pytest

from nigeria_economic_intelligence import spatial


def _grid(side: int) -> list[tuple[float, float]]:
    """A square lattice of points, spaced far enough apart to be stable."""
    return [
        (float(row), float(column))
        for row in range(side)
        for column in range(side)
    ]


def test_haversine_matches_a_known_distance():
    # One degree of latitude is about 111.2 km anywhere on the globe.
    assert spatial.haversine_km((0.0, 0.0), (1.0, 0.0)) == pytest.approx(
        111.2, abs=0.5
    )


def test_haversine_is_symmetric_and_zero_on_itself():
    lagos = (6.52, 3.38)
    kano = (12.00, 8.52)

    assert spatial.haversine_km(lagos, kano) == pytest.approx(
        spatial.haversine_km(kano, lagos)
    )
    assert spatial.haversine_km(lagos, lagos) == pytest.approx(0.0)


def test_knn_weights_rows_sum_to_one():
    weights = spatial.knn_weights(_grid(4), k=3)

    assert weights.shape == (16, 16)
    assert np.allclose(weights.sum(axis=1), 1.0)


def test_knn_weights_exclude_self():
    weights = spatial.knn_weights(_grid(3), k=2)

    assert np.allclose(np.diag(weights), 0.0)


def test_knn_weights_reject_impossible_k():
    points = _grid(2)

    with pytest.raises(ValueError, match="k must be between"):
        spatial.knn_weights(points, k=len(points))

    with pytest.raises(ValueError, match="k must be between"):
        spatial.knn_weights(points, k=0)


def test_morans_i_is_strongly_positive_when_values_are_segregated():
    """Half the lattice high, half low: about as clustered as it gets."""
    points = _grid(6)
    values = [0.0 if column < 3 else 1.0 for _, column in points]

    result = spatial.morans_i(
        values, spatial.knn_weights(points, 4), permutations=499
    )

    assert result.i > 0.6
    assert result.p_value < 0.05
    assert result.clustered


def test_morans_i_is_negative_when_values_alternate():
    """A chequerboard is the textbook case of negative autocorrelation."""
    points = _grid(6)
    values = [float((row + column) % 2) for row, column in points]

    result = spatial.morans_i(
        values, spatial.knn_weights(points, 4), permutations=499
    )

    assert result.i < 0
    assert not result.clustered


def test_morans_i_matches_a_value_computed_by_hand():
    """Four points in a line, k = 1, so every weight is known.

    With k = 1 each point's only neighbour is its nearest, giving the
    chain 0->1, 1->0, 2->3, 3->2 for values [1, 2, 10, 11]. Working the
    definition through by hand gives I = n/W * sum(w_ij z_i z_j) / sum(z_i^2).
    """
    points = [(0.0, 0.0), (0.0, 1.0), (0.0, 10.0), (0.0, 11.0)]
    values = np.array([1.0, 2.0, 10.0, 11.0])

    weights = spatial.knn_weights(points, k=1)
    deviations = values - values.mean()

    expected = (
        len(values) / weights.sum()
        * float(deviations @ weights @ deviations)
        / float((deviations**2).sum())
    )

    result = spatial.morans_i(values, weights, permutations=99)

    assert result.i == pytest.approx(expected)
    assert result.expected == pytest.approx(-1.0 / 3.0)


def test_morans_i_expectation_depends_only_on_n():
    points = _grid(5)
    values = np.arange(25, dtype=float)

    result = spatial.morans_i(
        values, spatial.knn_weights(points, 3), permutations=99
    )

    assert result.expected == pytest.approx(-1.0 / 24.0)


def test_permutation_p_value_can_never_be_zero():
    """A pseudo p-value of exactly zero would be a lie about the test."""
    points = _grid(5)
    values = [0.0 if column < 2 else 1.0 for _, column in points]

    result = spatial.morans_i(
        values, spatial.knn_weights(points, 3), permutations=199
    )

    assert result.p_value >= 1 / 200
    assert result.p_value > 0


def test_morans_i_is_reproducible_for_a_given_seed():
    points = _grid(4)
    values = np.linspace(0, 1, 16)
    weights = spatial.knn_weights(points, 3)

    first = spatial.morans_i(values, weights, permutations=299, seed=7)
    second = spatial.morans_i(values, weights, permutations=299, seed=7)

    assert first.p_value == second.p_value
    assert first.i == second.i


def test_morans_i_refuses_a_constant_series():
    points = _grid(3)

    with pytest.raises(ValueError, match="constant"):
        spatial.morans_i(
            [5.0] * 9, spatial.knn_weights(points, 2), permutations=9
        )


def test_morans_i_refuses_missing_values():
    points = _grid(3)
    values = [1.0, 2.0, math.nan, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0]

    with pytest.raises(ValueError, match="missing values"):
        spatial.morans_i(
            values, spatial.knn_weights(points, 2), permutations=9
        )


def test_morans_i_refuses_a_length_mismatch():
    points = _grid(3)

    with pytest.raises(ValueError, match="weights matrix"):
        spatial.morans_i(
            [1.0, 2.0], spatial.knn_weights(points, 2), permutations=9
        )


def test_moran_across_k_reports_every_k_requested():
    points = _grid(5)
    values = [0.0 if column < 2 else 1.0 for _, column in points]

    results = spatial.moran_across_k(
        values, points, neighbours=(2, 3, 4), permutations=99
    )

    assert [result.k for result in results] == [2, 3, 4]
    assert all(result.n == 25 for result in results)
