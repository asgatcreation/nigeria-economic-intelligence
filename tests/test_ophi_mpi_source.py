"""Tests for the OPHI multidimensional poverty connector.

The FCT P-code fix is the part worth testing hardest: it is the one
place the connector supplies a value the source does not, so it must
fail loudly if the source's shape ever changes.
"""

import csv

import pytest

from nigeria_economic_intelligence.ingestion import validate_dataframe
from nigeria_economic_intelligence.sources import ophi_mpi


COLUMNS = [
    "Country ISO3", "Admin 1 PCode", "Admin 1 Name", "MPI",
    "Headcount Ratio", "Intensity of Deprivation",
    "Vulnerable to Poverty", "In Severe Poverty",
]


def _row(pcode, name, mpi="0.1"):
    return {
        "Country ISO3": "NGA",
        "Admin 1 PCode": pcode,
        "Admin 1 Name": name,
        "MPI": mpi,
        "Headcount Ratio": "20.0",
        "Intensity of Deprivation": "50.0",
        "Vulnerable to Poverty": "15.0",
        "In Severe Poverty": "5.0",
    }


def _full_rows(fct_pcode=""):
    """One national row plus all 37 states, as the real file is shaped."""
    rows = [_row("", "")]
    for number in range(1, 38):
        code = f"NG{number:03d}"
        if code == ophi_mpi.FCT_PCODE:
            rows.append(_row(fct_pcode, "FCT"))
        else:
            rows.append(_row(code, f"State {number}"))
    return rows


def _write(tmp_path, rows, name="nga_mpi.csv"):
    path = tmp_path / name
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_fct_is_mapped_to_the_missing_pcode(tmp_path):
    path = _write(tmp_path, _full_rows())

    frame = ophi_mpi.build_dataframe(path)
    fct = frame[frame["geo_code"] == ophi_mpi.FCT_PCODE]

    assert not fct.empty
    assert set(fct["geo_name"]) == {"Federal Capital Territory"}
    assert set(fct["geo_level"]) == {"state"}


def test_all_thirty_seven_states_plus_the_nation_are_loaded(tmp_path):
    path = _write(tmp_path, _full_rows())

    frame = ophi_mpi.build_dataframe(path)

    states = frame[frame["geo_level"] == "state"]
    country = frame[frame["geo_level"] == "country"]

    assert states["geo_code"].nunique() == 37
    assert set(country["geo_code"]) == {"NGA"}


def test_the_national_row_is_kept_not_dropped(tmp_path):
    """It is what lets state figures be checked against the nation."""
    path = _write(tmp_path, _full_rows())

    frame = ophi_mpi.build_dataframe(path)

    assert (frame["geo_level"] == "country").sum() == len(
        ophi_mpi.INDICATORS
    )


def test_refuses_to_guess_when_the_gap_is_not_the_fct(tmp_path):
    """If another state also loses its code, the fix is unsafe."""
    rows = _full_rows()
    for row in rows:
        if row["Admin 1 PCode"] == "NG020":
            row["Admin 1 PCode"] = ""

    path = _write(tmp_path, rows)

    with pytest.raises(RuntimeError, match="Refusing to guess|without a P-code"):
        ophi_mpi.build_dataframe(path)


def test_refuses_when_an_unexpected_row_lacks_a_pcode(tmp_path):
    rows = _full_rows()
    rows.append(_row("", "Atlantis"))

    path = _write(tmp_path, rows)

    with pytest.raises(RuntimeError, match="without a P-code"):
        ophi_mpi.build_dataframe(path)


def test_uses_the_sources_own_pcode_when_it_is_present(tmp_path):
    """If OPHI later fills the field, the override must not fire."""
    path = _write(tmp_path, _full_rows(fct_pcode=ophi_mpi.FCT_PCODE))

    frame = ophi_mpi.build_dataframe(path)
    fct = frame[frame["geo_code"] == ophi_mpi.FCT_PCODE]

    assert not fct.empty


def test_output_passes_ingestion_validation(tmp_path):
    path = _write(tmp_path, _full_rows())

    frame = ophi_mpi.build_dataframe(path)
    validated = validate_dataframe(frame)

    assert len(validated) == len(frame)


def test_everything_is_flagged_as_a_survey_estimate(tmp_path):
    path = _write(tmp_path, _full_rows())

    frame = ophi_mpi.build_dataframe(path)

    assert set(frame["observation_status"]) == {"estimated"}
    assert all("survey estimate" in note for note in frame["notes"])


def test_domain_is_poverty(tmp_path):
    path = _write(tmp_path, _full_rows())

    frame = ophi_mpi.build_dataframe(path)

    assert set(frame["domain"]) == {"poverty"}


def test_missing_columns_fail_loudly(tmp_path):
    path = tmp_path / "truncated.csv"
    path.write_text("Country ISO3,MPI\nNGA,0.1\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="missing expected columns"):
        ophi_mpi.fetch_rows(path)


def test_blank_values_are_skipped_not_coerced(tmp_path):
    rows = _full_rows()
    rows[5]["In Severe Poverty"] = ""

    path = _write(tmp_path, rows)
    frame = ophi_mpi.build_dataframe(path)

    expected = len(rows) * len(ophi_mpi.INDICATORS) - 1
    assert len(frame) == expected
