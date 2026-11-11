"""Fetch Nigeria's state-level multidimensional poverty results from
OPHI (Oxford Poverty and Human Development Initiative), via HDX.

This is the state-level *economic* layer the rest of the project was
missing. Nigeria's own NBS publishes multidimensional poverty only as
PDF reports, and at senatorial-district rather than state level, so the
OPHI release -- computed from the same underlying survey and published
machine-readable with state P-codes -- is the usable source.

Two details are handled explicitly rather than silently:

* The file carries one national row (blank state name) alongside the 37
  state rows. It is loaded against the country geography, not dropped,
  because it lets a state aggregate be checked against the published
  national figure.
* The FCT row has no P-code. It is mapped to NG015, which is the only
  code absent from an otherwise complete NG001-NG037 sequence and is the
  FCT in this project's geography. The mapping is asserted at load time,
  so if OPHI ever fills that field or renumbers, the import fails rather
  than attaching poverty figures to the wrong state.

The underlying survey is MICS 2021, so these are survey estimates with
sampling error, not a census. They are stored as 'estimated'.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.request import urlopen
import csv
import io

import pandas as pd

DATASET_PAGE = "https://data.humdata.org/dataset/nigeria-mpi"
CSV_URL = (
    "https://data.humdata.org/dataset/"
    "042c1bf4-2942-475f-8cb2-1fb783f8da91/resource/"
    "601f51cd-c46a-4ab2-ba0f-8bef62329ddc/download/nga_mpi.csv"
)

SOURCE_CODE = "OPHI_MPI_NGA"
SOURCE_NAME = "Nigeria multidimensional poverty index (OPHI)"
ORGANIZATION = "Oxford Poverty and Human Development Initiative"
METHODOLOGY = (
    "Global MPI results for Nigeria computed by OPHI, University of "
    "Oxford, from MICS 2021, published via the Humanitarian Data "
    "Exchange. The MPI counts overlapping deprivations in health, "
    "education and living standards; a household is identified as poor "
    "when its weighted deprivation score reaches one third. Figures are "
    "survey estimates subject to sampling error, not a census."
)

SURVEY_YEAR = 2021
GEO_LEVEL = "state"
COUNTRY_CODE = "NGA"

# The FCT row ships without a P-code; NG015 is the only code missing
# from the otherwise complete sequence, and is the FCT in this project's
# geography seed. Verified at load time rather than assumed.
FCT_NAME = "FCT"
FCT_PCODE = "NG015"
EXPECTED_PCODES = {f"NG{number:03d}" for number in range(1, 38)}

SURVEY_NOTE = (
    "OPHI global MPI from MICS 2021; a survey estimate with sampling "
    "error, not a census."
)

REQUIRED_COLUMNS = (
    "Country ISO3",
    "Admin 1 PCode",
    "Admin 1 Name",
    "MPI",
    "Headcount Ratio",
    "Intensity of Deprivation",
    "Vulnerable to Poverty",
    "In Severe Poverty",
)


@dataclass(frozen=True)
class PovertyIndicator:
    column: str
    code: str
    name: str
    unit: str
    description: str


INDICATORS: tuple[PovertyIndicator, ...] = (
    PovertyIndicator(
        "MPI",
        "NGA_MPI",
        "Multidimensional poverty index",
        "index 0-1",
        (
            "Headcount ratio multiplied by intensity: the share of "
            "possible deprivations the population actually experiences."
        ),
    ),
    PovertyIndicator(
        "Headcount Ratio",
        "NGA_MPI_HEADCOUNT",
        "Multidimensionally poor population",
        "percent of population",
        (
            "Share of people deprived in at least one third of the "
            "weighted MPI indicators."
        ),
    ),
    PovertyIndicator(
        "Intensity of Deprivation",
        "NGA_MPI_INTENSITY",
        "Intensity of deprivation among the poor",
        "percent of weighted indicators",
        (
            "Average share of weighted indicators in which a "
            "multidimensionally poor person is deprived."
        ),
    ),
    PovertyIndicator(
        "Vulnerable to Poverty",
        "NGA_MPI_VULNERABLE",
        "Population vulnerable to multidimensional poverty",
        "percent of population",
        (
            "Share deprived in 20 to 33 percent of weighted indicators: "
            "not currently poor, but close to the threshold."
        ),
    ),
    PovertyIndicator(
        "In Severe Poverty",
        "NGA_MPI_SEVERE",
        "Population in severe multidimensional poverty",
        "percent of population",
        (
            "Share deprived in at least half of the weighted "
            "indicators."
        ),
    ),
)


def fetch_rows(path: str | Path | None = None) -> list[dict]:
    """Return the MPI rows from a local file or from HDX."""
    if path is not None:
        text = Path(path).read_text(encoding="utf-8-sig")
    else:
        with urlopen(CSV_URL, timeout=120) as response:
            text = response.read().decode("utf-8-sig")

    rows = list(csv.DictReader(io.StringIO(text)))

    if not rows:
        raise RuntimeError("The MPI source returned no rows.")

    missing = [
        column for column in REQUIRED_COLUMNS if column not in rows[0]
    ]
    if missing:
        raise RuntimeError(
            f"MPI source is missing expected columns: {missing}"
        )

    return rows


def _resolve_pcode(rows: list[dict]) -> dict[str, str]:
    """Map each state name to a P-code, filling in the FCT.

    Fails loudly if the shape of the file changes, rather than guessing.
    """
    named = [row for row in rows if row["Admin 1 Name"].strip()]
    coded = {
        row["Admin 1 Name"].strip(): row["Admin 1 PCode"].strip()
        for row in named
        if row["Admin 1 PCode"].strip()
    }

    uncoded = [
        row["Admin 1 Name"].strip()
        for row in named
        if not row["Admin 1 PCode"].strip()
    ]

    if not uncoded:
        return coded

    if uncoded != [FCT_NAME]:
        raise RuntimeError(
            f"Unexpected rows without a P-code: {uncoded}. "
            "Only the FCT is known to ship without one."
        )

    gap = EXPECTED_PCODES - set(coded.values())
    if gap != {FCT_PCODE}:
        raise RuntimeError(
            f"Expected {FCT_PCODE} to be the only missing P-code, "
            f"but the gap is {sorted(gap)}. Refusing to guess."
        )

    coded[FCT_NAME] = FCT_PCODE
    return coded


def build_dataframe(path: str | Path | None = None) -> pd.DataFrame:
    """Shape the MPI results for ingestion."""
    rows = fetch_rows(path)
    pcodes = _resolve_pcode(rows)

    records = []

    for row in rows:
        name = row["Admin 1 Name"].strip()

        if name:
            geo_code = pcodes[name]
            geo_name = (
                "Federal Capital Territory" if name == FCT_NAME else name
            )
            geo_level = GEO_LEVEL
        else:
            # The national row, kept so state figures can be checked
            # against the published national one.
            geo_code = COUNTRY_CODE
            geo_name = "Nigeria"
            geo_level = "country"

        for indicator in INDICATORS:
            raw = row[indicator.column].strip()
            if not raw:
                continue

            records.append(
                {
                    "source_code": SOURCE_CODE,
                    "source_name": SOURCE_NAME,
                    "organization": ORGANIZATION,
                    "source_url": DATASET_PAGE,
                    "methodology": METHODOLOGY,
                    "geo_code": geo_code,
                    "geo_name": geo_name,
                    "geo_level": geo_level,
                    "indicator_code": indicator.code,
                    "indicator_name": indicator.name,
                    "domain": "poverty",
                    "indicator_unit": indicator.unit,
                    "indicator_description": indicator.description,
                    "frequency": "irregular",
                    "period_start": f"{SURVEY_YEAR}-01-01",
                    "period_end": f"{SURVEY_YEAR}-12-31",
                    "value": float(raw),
                    "unit": indicator.unit,
                    "observation_status": "estimated",
                    "notes": SURVEY_NOTE,
                }
            )

    if not records:
        raise RuntimeError("The MPI source produced no observations.")

    frame = pd.DataFrame(records)
    return frame.sort_values(
        ["indicator_code", "geo_code"]
    ).reset_index(drop=True)


def write_csv(output: str | Path, path: str | Path | None = None) -> Path:
    """Fetch the MPI results and write an ingestible CSV."""
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
            "Fetch Nigeria state-level multidimensional poverty results "
            "from OPHI and write them as an ingestible CSV."
        )
    )
    parser.add_argument("--source-file", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument(
        "--ingest",
        action="store_true",
        help="Import the fetched file after writing it",
    )
    args = parser.parse_args()

    output = args.output or (
        PROJECT_ROOT / "data" / "raw"
        / f"ophi_mpi_{date.today().isoformat()}.csv"
    )

    print("Fetching Nigeria multidimensional poverty results:")
    path = write_csv(output, args.source_file)

    frame = pd.read_csv(path)
    print(
        f"  {frame['geo_code'].nunique()} geographies"
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
