"""Tests for the analysis layer.

The findings functions are tested against a constructed frame with known
answers rather than against live data, so a failure points at the
calculation rather than at a World Bank revision.
"""

import pandas as pd
import pytest

from nigeria_economic_intelligence import analysis


@pytest.fixture
def frame():
    """A small frame with deliberately known answers."""
    years = list(range(2000, 2011))

    return pd.DataFrame(
        {
            # Peaks at 2005 (200), ends at 180: a 10% shortfall.
            "NGA_GDP_PER_CAPITA": [
                100, 120, 140, 160, 180, 200,
                190, 185, 182, 181, 180,
            ],
            "NGA_GDP_GROWTH": [
                5.0, 5.0, 5.0, 5.0, 5.0, 5.0,
                1.0, 1.0, 1.0, 1.0, 1.0,
            ],
            # Exactly 2% population growth each year.
            "NGA_POPULATION": [100 * 1.02 ** n for n in range(11)],
            "NGA_INFLATION_CPI": [
                10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 25,
            ],
            "NGA_UNEMPLOYMENT": [4.0] * 10 + [3.0],
            "NGA_YOUTH_UNEMPLOYMENT": [8.0] * 10 + [6.0],
            "NGA_LABOUR_PARTICIPATION": [80.0] * 11,
            "NGA_VULNERABLE_EMPLOYMENT": [
                75, 74, 73, 72, 71, 70, 69, 68, 67, 66, 65,
            ],
            "NGA_EMPLOYMENT_AGRICULTURE": [
                50, 49, 48, 47, 46, 45, 44, 43, 42, 41, 40,
            ],
            "NGA_EMPLOYMENT_INDUSTRY": [
                10, 10, 10, 11, 11, 11, 12, 12, 12, 13, 13,
            ],
            "NGA_EMPLOYMENT_SERVICES": [
                40, 41, 42, 42, 43, 44, 44, 45, 46, 46, 47,
            ],
            "NGA_MANUF_VALUE_ADDED": [
                20, 18, 16, 14, 12, 10, 8, 6, 7, 8, 9,
            ],
            "NGA_AGRI_VALUE_ADDED": [25.0] * 11,
            "NGA_OIL_RENTS": [
                20, 18, 16, 14, 12, 10, 9, 8, 7, 6, 5,
            ],
        },
        index=pd.Index(years, name="year"),
    )


def test_growth_findings_identifies_peak_and_shortfall(frame):
    result = analysis.growth_findings(frame)

    assert result["peak_year"] == 2005
    assert result["peak_value"] == 200
    assert result["latest_year"] == 2010
    assert result["latest_value"] == 180
    assert result["shortfall_pct"] == pytest.approx(-10.0)
    # 2006 through 2010 all sit below the peak.
    assert result["years_below_peak"] == 5


def test_growth_findings_counts_years_below_population_growth(frame):
    result = analysis.growth_findings(frame)

    # From 2006 growth is 1% against 2% population growth.
    assert result["years_growth_below_population"] == 5


def test_price_findings_separates_recent_from_series_peak(frame):
    result = analysis.price_findings(frame)

    assert result["latest_year"] == 2010
    assert result["latest"] == 25
    assert result["series_peak"] == 28
    assert result["series_peak_year"] == 2009


def test_labour_findings_reports_the_paradox(frame):
    result = analysis.labour_findings(frame)

    assert result["unemployment"] == 3.0
    assert result["vulnerable"] == 65
    assert result["vulnerable_first"] == 75
    assert result["vulnerable_change"] == pytest.approx(-10.0)
    # The point of the finding: low unemployment, high insecurity.
    assert result["unemployment"] < 5
    assert result["vulnerable"] > 50


def test_structure_findings_measures_the_sectoral_shift(frame):
    result = analysis.structure_findings(frame)

    assert result["agriculture_shift"] == pytest.approx(-10.0)
    assert result["industry_shift"] == pytest.approx(3.0)
    assert result["services_shift"] == pytest.approx(7.0)


def test_structure_findings_tracks_manufacturing_decline(frame):
    result = analysis.structure_findings(frame)

    assert result["manufacturing_first"] == 20
    assert result["manufacturing_last"] == 9
    assert result["manufacturing_trough"] == 6
    assert result["manufacturing_trough_year"] == 2007


def test_structure_findings_correlation_is_finite(frame):
    result = analysis.structure_findings(frame)

    assert result["oil_growth_n"] == 11
    assert -1.0 <= result["oil_growth_correlation"] <= 1.0


def test_load_indicators_returns_real_annual_series():
    """Integration check against the live warehouse."""
    data = analysis.load_indicators()

    assert not data.empty
    assert data.index.name == "year"

    for code in (
        "NGA_GDP_PER_CAPITA",
        "NGA_UNEMPLOYMENT",
        "NGA_INFLATION_CPI",
    ):
        assert code in data.columns, f"{code} missing from warehouse"
        assert data[code].notna().sum() > 20


def test_findings_run_against_live_data():
    """The report's numbers must still compute from the warehouse."""
    data = analysis.load_indicators()

    growth = analysis.growth_findings(data)
    labour = analysis.labour_findings(data)
    structure = analysis.structure_findings(data)

    assert 1990 < growth["peak_year"] <= growth["latest_year"]
    assert 0 < labour["vulnerable"] <= 100
    assert 0 < labour["unemployment"] <= 100
    assert structure["agriculture_shift"] < 0


def test_load_states_returns_all_states_with_zones():
    states = analysis.load_states()

    assert len(states) == 37
    assert states["zone"].nunique() == 6
    assert states["state_code"].is_unique


def test_state_findings_identify_the_dependency_spread():
    states = analysis.load_states()
    findings = analysis.state_findings(states)

    assert findings["state_count"] == 37
    assert findings["lowest_value"] < findings["highest_value"]
    # Every state must land in a plausible demographic range.
    assert 30 < findings["lowest_value"] < 200
    assert 30 < findings["highest_value"] < 200
    assert len(findings["zone_summary"]) == 6


def test_state_populations_sum_to_the_national_total():
    """The state figures must reconcile with the published national one."""
    states = analysis.load_states()
    total = states["NGA_STATE_POPULATION"].sum()

    # Roughly 217 million on the 2022 projection.
    assert 2.0e8 < total < 2.4e8
