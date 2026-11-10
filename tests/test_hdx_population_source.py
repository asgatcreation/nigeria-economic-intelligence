"""Tests for the HDX state population connector.

The network is not used. A small fixture row with round numbers makes
the derived arithmetic checkable by hand.
"""

import csv

import pytest

from nigeria_economic_intelligence.ingestion import validate_dataframe
from nigeria_economic_intelligence.sources import hdx_population as hdx


def _row(**overrides) -> dict:
    """A state with 1,000 people in a deliberately simple structure.

    300 children (0-14), 600 working age (15-64), 100 elderly (65+),
    of whom 200 are aged 15-24. Dependency is therefore exactly
    (300 + 100) / 600 * 100 = 66.67.
    """
    row = {
        "ADM1_EN": "Testland",
        "ADM1_PCODE": "NG999",
        "T_TL": "1000",
        "F_TL": "480",
    }
    row.update({band: "100" for band in hdx.CHILD_BANDS})
    row.update({band: "60" for band in hdx.WORKING_AGE_BANDS})
    row.update({band: "25" for band in hdx.ELDERLY_BANDS})
    row.update(overrides)
    return row


@pytest.fixture
def source_file(tmp_path):
    path = tmp_path / "nga_admpop_adm1_2022.csv"
    row = _row()

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)

    return path


def test_derived_values_are_exact(source_file):
    frame = hdx.build_dataframe(source_file)
    values = dict(zip(frame["indicator_code"], frame["value"]))

    assert values["NGA_STATE_POPULATION"] == 1000
    assert values["NGA_STATE_WORKING_AGE_POPULATION"] == 600
    assert values["NGA_STATE_WORKING_AGE_SHARE"] == pytest.approx(60.0)
    assert values["NGA_STATE_YOUTH_SHARE"] == pytest.approx(12.0)
    assert values["NGA_STATE_FEMALE_SHARE"] == pytest.approx(48.0)
    # (300 children + 100 elderly) / 600 working age.
    assert values["NGA_STATE_DEPENDENCY_RATIO"] == pytest.approx(
        66.6667, abs=1e-3
    )


def test_output_passes_ingestion_validation(source_file):
    frame = hdx.build_dataframe(source_file)

    validated = validate_dataframe(frame)

    assert len(validated) == len(frame) == len(hdx.DERIVED)


def test_everything_is_flagged_as_an_estimate(source_file):
    """Nigeria's last census was 2006; these are projections."""
    frame = hdx.build_dataframe(source_file)

    assert set(frame["observation_status"]) == {"estimated"}
    assert all("2006 census" in note for note in frame["notes"])


def test_geography_is_state_level_with_a_pcode(source_file):
    frame = hdx.build_dataframe(source_file)

    assert set(frame["geo_level"]) == {"state"}
    assert set(frame["geo_code"]) == {"NG999"}


def test_period_covers_the_reference_year(source_file):
    frame = hdx.build_dataframe(source_file)

    assert set(frame["period_start"]) == {f"{hdx.REFERENCE_YEAR}-01-01"}
    assert set(frame["period_end"]) == {f"{hdx.REFERENCE_YEAR}-12-31"}


def test_every_derived_indicator_records_its_formula():
    """A reader must be able to check any figure against the source."""
    for indicator in hdx.DERIVED:
        assert indicator.description.strip().endswith(".")
        assert len(indicator.description) > 20


def test_missing_columns_fail_loudly(tmp_path):
    path = tmp_path / "truncated.csv"
    path.write_text("ADM1_EN,ADM1_PCODE\nTestland,NG999\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="missing expected columns"):
        hdx.fetch_rows(path)


def test_an_empty_source_fails_loudly(tmp_path):
    path = tmp_path / "empty.csv"
    path.write_text("ADM1_EN,ADM1_PCODE\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="no rows"):
        hdx.fetch_rows(path)


def test_a_row_without_a_state_code_fails_loudly(tmp_path):
    path = tmp_path / "nameless.csv"
    row = _row(ADM1_PCODE="")

    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(row))
        writer.writeheader()
        writer.writerow(row)

    with pytest.raises(RuntimeError, match="no state code"):
        hdx.build_dataframe(path)
