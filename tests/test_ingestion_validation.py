import pandas as pd
import pytest

from nigeria_economic_intelligence.ingestion import validate_dataframe


@pytest.fixture
def valid_data():
    return pd.DataFrame(
        [
            {
                "source_code": "TEST_SOURCE",
                "source_name": "Test Source",
                "geo_code": "NG-TEST",
                "geo_name": "Test Geography",
                "geo_level": "other",
                "indicator_code": "TEST_INDICATOR",
                "indicator_name": "Test Indicator",
                "domain": "prices",
                "period_start": "2026-01-01",
                "period_end": "2026-01-31",
                "value": 12.5,
            }
        ]
    )


def test_valid_data_passes_validation(valid_data):
    result = validate_dataframe(valid_data)

    assert len(result) == 1
    assert result.loc[0, "indicator_code"] == "TEST_INDICATOR"
    assert result.loc[0, "value"] == 12.5


def test_missing_required_column_is_rejected(valid_data):
    valid_data = valid_data.drop(columns=["indicator_code"])

    with pytest.raises(ValueError, match="Missing required columns"):
        validate_dataframe(valid_data)


def test_invalid_date_is_rejected(valid_data):
    valid_data.loc[0, "period_start"] = "not-a-date"

    with pytest.raises(ValueError, match="Invalid dates"):
        validate_dataframe(valid_data)


def test_period_end_before_start_is_rejected(valid_data):
    valid_data.loc[0, "period_start"] = "2026-02-01"
    valid_data.loc[0, "period_end"] = "2026-01-31"

    with pytest.raises(ValueError, match="Period end precedes"):
        validate_dataframe(valid_data)


def test_non_numeric_value_is_rejected(valid_data):
    valid_data["value"] = valid_data["value"].astype(object)
    valid_data.loc[0, "value"] = "not-a-number"

    with pytest.raises(ValueError, match="numeric values"):
        validate_dataframe(valid_data)


def test_invalid_geography_level_is_rejected(valid_data):
    valid_data.loc[0, "geo_level"] = "province"

    with pytest.raises(ValueError, match="geo_level"):
        validate_dataframe(valid_data)


def test_duplicate_observations_in_same_csv_are_rejected(valid_data):
    duplicated = pd.concat(
        [valid_data, valid_data],
        ignore_index=True,
    )

    with pytest.raises(ValueError, match="Duplicate observations"):
        validate_dataframe(duplicated)


def test_empty_dataframe_is_rejected(valid_data):
    empty_data = valid_data.iloc[0:0]

    with pytest.raises(ValueError, match="no observations"):
        validate_dataframe(empty_data)




def test_blank_indicator_code_is_rejected(valid_data):
    valid_data.loc[0, "indicator_code"] = ""

    with pytest.raises(ValueError):
        validate_dataframe(valid_data)


def test_invalid_observation_status_is_rejected(valid_data):
    valid_data["observation_status"] = "unverified"

    with pytest.raises(ValueError, match="observation_status"):
        validate_dataframe(valid_data)


def test_infinite_value_is_rejected(valid_data):
    valid_data.loc[0, "value"] = float("inf")

    with pytest.raises(ValueError):
        validate_dataframe(valid_data)
