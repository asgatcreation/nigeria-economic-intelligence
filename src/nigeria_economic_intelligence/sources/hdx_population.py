"""Fetch Nigeria's state-level population structure from the
humanitarian Common Operational Dataset (COD-PS) published on HDX.

Nigeria's last census was in 2006. Every current population figure for
Nigeria, including this one, is therefore a *projection* from that
baseline rather than a count. All observations here are stored with
observation_status 'estimated' and a note saying so. This is not
pedantry: state-level projections carry real uncertainty, and the
political salience of state population figures in Nigeria -- they feed
revenue allocation and constituency delimitation -- is precisely why the
provenance has to travel with the numbers.

The source publishes counts by five-year age band and sex. The derived
shares and ratios below are exact arithmetic on those published counts,
with each formula recorded in the indicator description, so a reader can
check any figure against the source file.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.request import urlopen
import csv
import io

import pandas as pd

DATASET_PAGE = "https://data.humdata.org/dataset/cod-ps-nga"
CSV_URL = (
    "https://data.humdata.org/dataset/"
    "a7c3de5e-ff27-4746-99cd-05f2ad9b1066/resource/"
    "d9fc551a-b5e4-4bed-9d0d-b047b6961817/download/"
    "nga_admpop_adm1_2022.csv"
)

SOURCE_CODE = "HDX_COD_PS_NGA"
SOURCE_NAME = "Nigeria subnational population statistics (COD-PS)"
ORGANIZATION = "UNFPA and United States Census Bureau"
METHODOLOGY = (
    "Common Operational Dataset for population statistics (COD-PS), "
    "Nigeria, reference year 2022, published via the Humanitarian Data "
    "Exchange. Population by five-year age band and sex at admin level "
    "1 (state). Figures are projections from the 2006 census, Nigeria's "
    "most recent, and are estimates rather than enumerated counts. "
    "Shares and ratios are computed from the published age-band counts."
)

REFERENCE_YEAR = 2022
GEO_LEVEL = "state"
PROJECTION_NOTE = (
    "Projected from the 2006 census, Nigeria's most recent; an estimate, "
    "not an enumerated count."
)

CHILD_BANDS = ("T_00_04", "T_05_09", "T_10_14")
WORKING_AGE_BANDS = (
    "T_15_19", "T_20_24", "T_25_29", "T_30_34", "T_35_39",
    "T_40_44", "T_45_49", "T_50_54", "T_55_59", "T_60_64",
)
YOUTH_BANDS = ("T_15_19", "T_20_24")
ELDERLY_BANDS = ("T_65_69", "T_70_74", "T_75_79", "T_80Plus")

REQUIRED_COLUMNS = (
    ("ADM1_EN", "ADM1_PCODE", "T_TL", "F_TL")
    + CHILD_BANDS
    + WORKING_AGE_BANDS
    + ELDERLY_BANDS
)


def _total(row: dict, bands) -> float:
    return float(sum(float(row[band]) for band in bands))


@dataclass(frozen=True)
class DerivedIndicator:
    """An indicator computed from the published age-band counts."""

    code: str
    name: str
    unit: str
    description: str
    compute: Callable[[dict], float]


DERIVED: tuple[DerivedIndicator, ...] = (
    DerivedIndicator(
        "NGA_STATE_POPULATION",
        "State population",
        "persons",
        "Published total population (T_TL).",
        lambda row: float(row["T_TL"]),
    ),
    DerivedIndicator(
        "NGA_STATE_WORKING_AGE_POPULATION",
        "State working-age population, 15-64",
        "persons",
        "Sum of published five-year age bands from 15-19 to 60-64.",
        lambda row: _total(row, WORKING_AGE_BANDS),
    ),
    DerivedIndicator(
        "NGA_STATE_WORKING_AGE_SHARE",
        "State working-age share of population",
        "percent of population",
        "Population aged 15-64 divided by total population, times 100.",
        lambda row: (
            _total(row, WORKING_AGE_BANDS) / float(row["T_TL"]) * 100
        ),
    ),
    DerivedIndicator(
        "NGA_STATE_YOUTH_SHARE",
        "State youth share of population, 15-24",
        "percent of population",
        "Population aged 15-24 divided by total population, times 100.",
        lambda row: _total(row, YOUTH_BANDS) / float(row["T_TL"]) * 100,
    ),
    DerivedIndicator(
        "NGA_STATE_DEPENDENCY_RATIO",
        "State age dependency ratio",
        "dependants per 100 people aged 15-64",
        (
            "Population aged 0-14 plus 65 and over, divided by "
            "population aged 15-64, times 100."
        ),
        lambda row: (
            (_total(row, CHILD_BANDS) + _total(row, ELDERLY_BANDS))
            / _total(row, WORKING_AGE_BANDS)
            * 100
        ),
    ),
    DerivedIndicator(
        "NGA_STATE_FEMALE_SHARE",
        "State female share of population",
        "percent of population",
        "Published female total (F_TL) divided by total population.",
        lambda row: float(row["F_TL"]) / float(row["T_TL"]) * 100,
    ),
)


def fetch_rows(path: str | Path | None = None) -> list[dict]:
    """Return the admin-1 population rows, from a local file or HDX."""
    if path is not None:
        text = Path(path).read_text(encoding="utf-8-sig")
    else:
        with urlopen(CSV_URL, timeout=120) as response:
            text = response.read().decode("utf-8-sig")

    rows = list(csv.DictReader(io.StringIO(text)))

    if not rows:
        raise RuntimeError("The population source returned no rows.")

    missing = [
        column for column in REQUIRED_COLUMNS if column not in rows[0]
    ]
    if missing:
        raise RuntimeError(
            f"Population source is missing expected columns: {missing}"
        )

    return rows


def build_dataframe(path: str | Path | None = None) -> pd.DataFrame:
    """Shape the state population data for ingestion."""
    rows = fetch_rows(path)

    records = []

    for row in rows:
        pcode = row["ADM1_PCODE"].strip()
        name = row["ADM1_EN"].strip()

        if not pcode or not name:
            raise RuntimeError(f"Row with no state code or name: {row!r:.120}")

        for indicator in DERIVED:
            records.append(
                {
                    "source_code": SOURCE_CODE,
                    "source_name": SOURCE_NAME,
                    "organization": ORGANIZATION,
                    "source_url": DATASET_PAGE,
                    "methodology": METHODOLOGY,
                    "geo_code": pcode,
                    "geo_name": name,
                    "geo_level": GEO_LEVEL,
                    "indicator_code": indicator.code,
                    "indicator_name": indicator.name,
                    "domain": "demographics",
                    "indicator_unit": indicator.unit,
                    "indicator_description": indicator.description,
                    "frequency": "annual",
                    "period_start": f"{REFERENCE_YEAR}-01-01",
                    "period_end": f"{REFERENCE_YEAR}-12-31",
                    "value": round(indicator.compute(row), 4),
                    "unit": indicator.unit,
                    "observation_status": "estimated",
                    "notes": PROJECTION_NOTE,
                }
            )

    frame = pd.DataFrame(records)
    return frame.sort_values(
        ["indicator_code", "geo_code"]
    ).reset_index(drop=True)


def write_csv(output: str | Path, path: str | Path | None = None) -> Path:
    """Fetch the state population data and write an ingestible CSV."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    build_dataframe(path).to_csv(output, index=False)

    return output


def main() -> None:
    import argparse
    from datetime import date

    from ..config import PROJECT_ROOT

    parser = argparse.ArgumentParser(
        description=(
            "Fetch Nigeria state-level population structure from HDX "
            "and write it as an ingestible CSV."
        )
    )
    parser.add_argument(
        "--source-file",
        default=None,
        help="Use a local copy of nga_admpop_adm1_2022.csv instead of HDX",
    )
    parser.add_argument("--output", default=None)
    parser.add_argument(
        "--ingest",
        action="store_true",
        help="Import the fetched file after writing it",
    )
    args = parser.parse_args()

    output = args.output or (
        PROJECT_ROOT / "data" / "raw"
        / f"hdx_state_population_{date.today().isoformat()}.csv"
    )

    print("Fetching Nigeria state population structure:")
    path = write_csv(output, args.source_file)

    frame = pd.read_csv(path)
    print(
        f"  {frame['geo_code'].nunique()} states"
        f" x {frame['indicator_code'].nunique()} indicators"
        f" = {len(frame)} observations"
    )
    print(f"Wrote {path}")

    if args.ingest:
        from ..ingestion import ingest_csv

        batch_id, count = ingest_csv(path)
        print(f"Imported {count} observations as batch {batch_id}.")


if __name__ == "__main__":
    main()
