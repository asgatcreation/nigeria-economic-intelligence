"""Tests for the Phase 2 statistics: intervals and the interaction model.

Both are tested against constructed data whose answer is known by
construction, so a failure points at the implementation rather than at a
revision to the published figures. The checks against the live warehouse
are marked `warehouse` and are the ones CI cannot run.
"""

import numpy as np
import pandas as pd
import pytest

from nigeria_economic_intelligence import analysis


@pytest.fixture
def correlated():
    """x and y with a strong, known positive relationship."""
    generator = np.random.default_rng(11)
    x = generator.normal(size=60)
    y = 0.9 * x + generator.normal(scale=0.4, size=60)
    return x, y


@pytest.fixture
def independent():
    generator = np.random.default_rng(12)
    return generator.normal(size=60), generator.normal(size=60)


def test_interval_brackets_the_point_estimate(correlated):
    result = analysis.correlation_interval(*correlated, draws=2000)

    assert result["bootstrap_low"] < result["r"] < result["bootstrap_high"]
    assert result["fisher_low"] < result["r"] < result["fisher_high"]


def test_the_two_methods_broadly_agree(correlated):
    """They assume different things; on well-behaved data they should agree."""
    result = analysis.correlation_interval(*correlated, draws=4000)

    assert result["bootstrap_low"] == pytest.approx(
        result["fisher_low"], abs=0.1
    )
    assert result["bootstrap_high"] == pytest.approx(
        result["fisher_high"], abs=0.1
    )


def test_independent_series_give_an_interval_containing_zero(independent):
    result = analysis.correlation_interval(*independent, draws=2000)

    assert result["includes_zero"]
    assert result["bootstrap_low"] < 0 < result["bootstrap_high"]


def test_a_strong_relationship_excludes_zero(correlated):
    result = analysis.correlation_interval(*correlated, draws=2000)

    assert not result["includes_zero"]
    assert result["bootstrap_low"] > 0


def test_intervals_narrow_as_the_sample_grows():
    """The whole point of reporting them: n = 17 buys very little."""
    generator = np.random.default_rng(13)
    big_x = generator.normal(size=400)
    big_y = 0.6 * big_x + generator.normal(scale=0.8, size=400)

    small = analysis.correlation_interval(
        big_x[:17], big_y[:17], draws=2000
    )
    large = analysis.correlation_interval(big_x, big_y, draws=2000)

    # The bound is loose on purpose: the two subsets have different
    # sample correlations, and interval width depends on r as well as
    # n, so anything tighter would be testing this particular seed.
    assert large["width"] < 0.7 * small["width"]
    assert small["width"] > 0.15


def test_the_bootstrap_is_reproducible(correlated):
    first = analysis.correlation_interval(*correlated, draws=1500, seed=3)
    second = analysis.correlation_interval(*correlated, draws=1500, seed=3)

    assert first["bootstrap_low"] == second["bootstrap_low"]
    assert first["bootstrap_high"] == second["bootstrap_high"]


def test_interval_refuses_too_few_pairs():
    with pytest.raises(ValueError, match="at least 4 pairs"):
        analysis.correlation_interval([1.0, 2.0], [3.0, 4.0])


def test_interval_refuses_mismatched_series():
    with pytest.raises(ValueError, match="equal length"):
        analysis.correlation_interval([1.0, 2.0, 3.0, 4.0], [1.0, 2.0])


def _designed_states(south_slope: float, north_slope: float) -> pd.DataFrame:
    """A states frame whose two slopes are exactly what we ask for."""
    rows = []
    for index in range(18):
        dependency = 60.0 + index
        rows.append(
            {
                "state_code": f"NGS{index:03d}",
                "state": f"South {index}",
                "zone": "South West",
                "NGA_STATE_DEPENDENCY_RATIO": dependency,
                "NGA_MPI_HEADCOUNT": 5.0 + south_slope * dependency,
            }
        )
    for index in range(19):
        dependency = 80.0 + index
        rows.append(
            {
                "state_code": f"NGN{index:03d}",
                "state": f"North {index}",
                "zone": "North West",
                "NGA_STATE_DEPENDENCY_RATIO": dependency,
                "NGA_MPI_HEADCOUNT": -40.0 + north_slope * dependency,
            }
        )
    return pd.DataFrame(rows)


def test_model_recovers_slopes_it_was_built_from():
    model = analysis.poverty_model(_designed_states(0.0, 1.5))

    assert model["southern_slope"] == pytest.approx(0.0, abs=1e-6)
    assert model["northern_slope"] == pytest.approx(1.5, abs=1e-6)
    assert model["slope_difference"] == pytest.approx(1.5, abs=1e-6)


def test_model_finds_no_difference_when_the_slopes_are_equal():
    model = analysis.poverty_model(_designed_states(0.8, 0.8))

    assert model["slope_difference"] == pytest.approx(0.0, abs=1e-6)


def test_model_reports_the_interaction_as_the_slope_difference():
    model = analysis.poverty_model(_designed_states(0.2, 1.1))

    assert (
        model["terms"]["dependency:north"]["estimate"]
        == pytest.approx(model["slope_difference"])
    )
    assert (
        model["southern_slope"] + model["slope_difference"]
        == pytest.approx(model["northern_slope"])
    )


def test_model_reports_both_robust_and_classical_errors():
    """Robust errors that are never compared are a claim, not a check."""
    model = analysis.poverty_model(_designed_states(0.2, 1.1))

    for term in model["terms"].values():
        assert term["robust_se"] >= 0
        assert term["classical_se"] >= 0


def test_diagnostics_cover_every_state_exactly_once():
    states = _designed_states(0.2, 1.1)
    model = analysis.poverty_model(states)

    assert len(model["diagnostics"]) == len(states)
    assert set(model["diagnostics"]["state"]) == set(states["state"])
    assert model["diagnostics"]["cooks_d"].is_monotonic_decreasing


def test_leverage_sums_to_the_number_of_parameters():
    """A standard identity: trace of the hat matrix is rank of the design."""
    model = analysis.poverty_model(_designed_states(0.2, 1.1))

    assert model["diagnostics"]["leverage"].sum() == pytest.approx(4.0)


def test_an_outlier_is_flagged_as_influential():
    states = _designed_states(0.2, 1.1)
    states.loc[states["state"] == "North 9", "NGA_MPI_HEADCOUNT"] += 40

    model = analysis.poverty_model(states)

    assert "North 9" in set(model["influential"]["state"])
    assert model["refit_n"] == len(states) - len(model["influential"])


@pytest.mark.warehouse
def test_live_intervals_cover_the_three_reported_groups():
    intervals = analysis.poverty_intervals(analysis.load_states())

    assert set(intervals) == {"pooled", "north", "south"}
    assert intervals["pooled"]["n"] == 37
    assert (
        intervals["north"]["n"] + intervals["south"]["n"] == 37
    )
    for row in intervals.values():
        assert row["bootstrap_low"] <= row["r"] <= row["bootstrap_high"]


@pytest.mark.warehouse
def test_live_model_finds_a_steeper_northern_slope():
    model = analysis.poverty_model(analysis.load_states())

    assert model["n"] == 37
    assert model["northern_slope"] > model["southern_slope"]
    assert model["slope_difference_p"] < 0.05
    # The reported conclusion must not depend on the influential states.
    assert model["refit_difference_p"] < 0.05


@pytest.mark.warehouse
def test_live_spatial_findings_cover_both_measures():
    result = analysis.spatial_findings(analysis.load_states())

    assert set(result["measures"]) == {"poverty", "dependency"}
    for measure in result["measures"].values():
        headline = measure["headline"]
        assert headline.n == 37
        assert -1.0 <= headline.i <= 1.0
        assert headline.p_value > 0
        assert len(measure["sensitivity"]) == 5


@pytest.mark.warehouse
def test_live_poverty_is_spatially_clustered():
    result = analysis.spatial_findings(analysis.load_states())

    assert result["measures"]["poverty"]["headline"].clustered
    assert result["measures"]["dependency"]["headline"].clustered


@pytest.mark.warehouse
def test_every_state_in_the_warehouse_has_a_boundary():
    """A missing boundary would silently drop a state from the maps."""
    states = analysis.load_states()
    result = analysis.spatial_findings(states)

    assert set(states["state_code"]) <= set(result["boundaries"])
