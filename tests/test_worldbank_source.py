"""Tests for the World Bank connector.

The API is not called here. Shaping is tested against a captured
response so the suite stays offline and deterministic; the live fetch is
exercised by running the connector itself.
"""

import pandas as pd
import pytest

from nigeria_economic_intelligence.ingestion import validate_dataframe
from nigeria_economic_intelligence.sources import worldbank


def test_indicator_codes_are_unique():
    codes = [i.indicator_code for i in worldbank.INDICATORS]
    wb_codes = [i.wb_code for i in worldbank.INDICATORS]

    assert len(codes) == len(set(codes))
    assert len(wb_codes) == len(set(wb_codes))


def test_every_indicator_uses_a_schema_allowed_domain():
    from nigeria_economic_intelligence.ingestion import ALLOWED_DOMAINS

    for indicator in worldbank.INDICATORS:
        assert indicator.domain in ALLOWED_DOMAINS, (
            f"{indicator.indicator_code} has domain "
            f"{indicator.domain!r}, which the schema rejects"
        )


def test_modelled_series_are_flagged_as_estimated():
    modelled = [i for i in worldbank.INDICATORS if i.modelled]

    assert modelled, "expected some modelled series"

    for indicator in modelled:
        assert indicator.observation_status == "estimated"
        assert "ILO modelled" in indicator.notes
        assert "NBS" in indicator.notes


def test_measured_series_are_flagged_as_observed():
    for indicator in worldbank.INDICATORS:
        if not indicator.modelled:
            assert indicator.observation_status == "observed"


def test_labour_market_series_are_all_modelled():
    """Every labour series here is an ILO estimate; none is a survey."""
    for indicator in worldbank.INDICATORS:
        if indicator.domain == "labour_market":
            assert indicator.modelled, (
                f"{indicator.indicator_code} is a labour series not "
                "marked as modelled"
            )


def test_build_dataframe_output_passes_ingestion_validation(monkeypatch):
    """The connector's output must satisfy the ingestion contract."""

    def fake_fetch(indicator, start_year=0, end_year=0):
        return [
            {"date": str(year), "value": 10.0 + year % 7}
            for year in (2021, 2022, 2023)
        ]

    monkeypatch.setattr(worldbank, "fetch_series", fake_fetch)

    frame = worldbank.build_dataframe()

    assert len(frame) == 3 * len(worldbank.INDICATORS)

    # The real contract: it must survive the validator unchanged.
    validated = validate_dataframe(frame)
    assert len(validated) == len(frame)


def test_build_dataframe_sets_annual_period_bounds(monkeypatch):
    monkeypatch.setattr(
        worldbank,
        "fetch_series",
        lambda indicator, start_year=0, end_year=0: [
            {"date": "2023", "value": 1.0}
        ],
    )

    frame = worldbank.build_dataframe()

    assert set(frame["period_start"]) == {"2023-01-01"}
    assert set(frame["period_end"]) == {"2023-12-31"}
    assert set(frame["frequency"]) == {"annual"}
    assert set(frame["geo_code"]) == {"NGA"}
    assert set(frame["geo_level"]) == {"country"}


def test_build_dataframe_rejects_an_empty_api_result(monkeypatch):
    monkeypatch.setattr(
        worldbank,
        "fetch_series",
        lambda indicator, start_year=0, end_year=0: [],
    )

    with pytest.raises(RuntimeError, match="no observations"):
        worldbank.build_dataframe()


def test_fetch_series_rejects_a_paginated_response(monkeypatch):
    """A truncated response must fail loudly, not silently lose rows."""
    monkeypatch.setattr(
        worldbank,
        "_request",
        lambda url, attempts=3: [
            {"page": 1, "pages": 3},
            [{"date": "2023", "value": 1.0}],
        ],
    )

    with pytest.raises(RuntimeError, match="pages"):
        worldbank.fetch_series(worldbank.INDICATORS[0])


def test_fetch_series_rejects_a_null_payload(monkeypatch):
    monkeypatch.setattr(
        worldbank,
        "_request",
        lambda url, attempts=3: [{"page": 1, "pages": 1}, None],
    )

    with pytest.raises(RuntimeError, match="No data"):
        worldbank.fetch_series(worldbank.INDICATORS[0])


def test_fetch_series_drops_null_values(monkeypatch):
    monkeypatch.setattr(
        worldbank,
        "_request",
        lambda url, attempts=3: [
            {"page": 1, "pages": 1},
            [
                {"date": "2023", "value": 1.0},
                {"date": "2024", "value": None},
            ],
        ],
    )

    series = worldbank.fetch_series(worldbank.INDICATORS[0])

    assert len(series) == 1
    assert series[0]["date"] == "2023"
