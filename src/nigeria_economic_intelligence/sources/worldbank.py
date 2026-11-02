"""Fetch Nigeria indicators from the World Bank's World Development
Indicators (WDI) API.

The connector writes a CSV in the project's own ingestion format rather
than inserting rows directly. Everything therefore passes through the
same validation, transaction handling and batch tracking as any other
import, and the fetched file is retained as the raw artefact the import
can be reproduced from.

A deliberate caveat is carried into the database: several labour-market
series are ILO *modelled* estimates, not Nigeria's own published survey
results. Those are stored with observation_status 'estimated' so that
analysis can distinguish them from directly measured figures. Nigeria's
National Bureau of Statistics revised its labour-force methodology in
2023, and its headline unemployment rate is not comparable with the
modelled series here.
"""

from datetime import date
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen
import json
import time

import pandas as pd

API_ROOT = "https://api.worldbank.org/v2"
COUNTRY = "NGA"

SOURCE_CODE = "WORLDBANK_WDI"
SOURCE_NAME = "World Development Indicators"
ORGANIZATION = "World Bank"
SOURCE_URL = "https://databank.worldbank.org/source/world-development-indicators"
METHODOLOGY = (
    "World Bank World Development Indicators, retrieved from the public "
    "API v2. Series compiled by the World Bank from national accounts, "
    "national statistical offices and international agencies. Labour "
    "market series marked as modelled are ILO modelled estimates, not "
    "Nigerian survey results."
)

GEO_CODE = "NGA"
GEO_NAME = "Nigeria"
GEO_LEVEL = "country"

# Marks series that are modelled rather than directly measured. These are
# stored as 'estimated' so analysis can treat them with due caution.
MODELLED_NOTE = (
    "ILO modelled estimate, not a Nigerian survey result. Not comparable "
    "with NBS published figures, especially after the 2023 NBS "
    "labour-force methodology revision."
)

STANDARD_NOTE = "World Bank compiled series."


class Indicator:
    """One World Bank series mapped onto this project's schema."""

    def __init__(
        self,
        wb_code: str,
        indicator_code: str,
        indicator_name: str,
        domain: str,
        unit: str,
        *,
        modelled: bool = False,
    ) -> None:
        self.wb_code = wb_code
        self.indicator_code = indicator_code
        self.indicator_name = indicator_name
        self.domain = domain
        self.unit = unit
        self.modelled = modelled

    @property
    def observation_status(self) -> str:
        return "estimated" if self.modelled else "observed"

    @property
    def notes(self) -> str:
        return MODELLED_NOTE if self.modelled else STANDARD_NOTE


# Curated set: enough to characterise growth, prices, the labour market
# and the structure of the economy, without padding.
INDICATORS: tuple[Indicator, ...] = (
    Indicator(
        "NY.GDP.MKTP.KD.ZG", "NGA_GDP_GROWTH",
        "GDP growth", "economy", "annual percent",
    ),
    Indicator(
        "NY.GDP.PCAP.KD", "NGA_GDP_PER_CAPITA",
        "GDP per capita", "economy", "constant 2015 USD",
    ),
    Indicator(
        "FP.CPI.TOTL.ZG", "NGA_INFLATION_CPI",
        "Inflation, consumer prices", "prices", "annual percent",
    ),
    Indicator(
        "NY.GDP.PETR.RT.ZS", "NGA_OIL_RENTS",
        "Oil rents", "economy", "percent of GDP",
    ),
    Indicator(
        "NV.AGR.TOTL.ZS", "NGA_AGRI_VALUE_ADDED",
        "Agriculture, forestry and fishing value added",
        "agriculture", "percent of GDP",
    ),
    Indicator(
        "NV.IND.MANF.ZS", "NGA_MANUF_VALUE_ADDED",
        "Manufacturing value added", "economy", "percent of GDP",
    ),
    Indicator(
        "SP.POP.TOTL", "NGA_POPULATION",
        "Population, total", "demographics", "persons",
    ),
    Indicator(
        "SL.UEM.TOTL.ZS", "NGA_UNEMPLOYMENT",
        "Unemployment rate", "labour_market",
        "percent of labour force", modelled=True,
    ),
    Indicator(
        "SL.UEM.1524.ZS", "NGA_YOUTH_UNEMPLOYMENT",
        "Youth unemployment rate, ages 15-24", "labour_market",
        "percent of labour force aged 15-24", modelled=True,
    ),
    Indicator(
        "SL.TLF.CACT.ZS", "NGA_LABOUR_PARTICIPATION",
        "Labour force participation rate, ages 15+", "labour_market",
        "percent of population aged 15+", modelled=True,
    ),
    Indicator(
        "SL.AGR.EMPL.ZS", "NGA_EMPLOYMENT_AGRICULTURE",
        "Employment in agriculture", "labour_market",
        "percent of total employment", modelled=True,
    ),
    Indicator(
        "SL.IND.EMPL.ZS", "NGA_EMPLOYMENT_INDUSTRY",
        "Employment in industry", "labour_market",
        "percent of total employment", modelled=True,
    ),
    Indicator(
        "SL.SRV.EMPL.ZS", "NGA_EMPLOYMENT_SERVICES",
        "Employment in services", "labour_market",
        "percent of total employment", modelled=True,
    ),
    Indicator(
        "SL.EMP.VULN.ZS", "NGA_VULNERABLE_EMPLOYMENT",
        "Vulnerable employment", "labour_market",
        "percent of total employment", modelled=True,
    ),
)

DEFAULT_START_YEAR = 1991
DEFAULT_END_YEAR = date.today().year


def _request(url: str, *, attempts: int = 3) -> list:
    """GET a JSON URL, retrying transient failures."""
    last_error: Exception | None = None

    for attempt in range(attempts):
        try:
            with urlopen(url, timeout=60) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # network or decode failure
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(2 * (attempt + 1))

    raise RuntimeError(f"Request failed after {attempts} attempts: {url}") from last_error


def fetch_series(
    indicator: Indicator,
    start_year: int = DEFAULT_START_YEAR,
    end_year: int = DEFAULT_END_YEAR,
) -> list[dict]:
    """Return the non-null observations for one indicator."""
    query = urlencode(
        {
            "format": "json",
            "per_page": 20000,
            "date": f"{start_year}:{end_year}",
        }
    )
    url = f"{API_ROOT}/country/{COUNTRY}/indicator/{indicator.wb_code}?{query}"

    payload = _request(url)

    if not isinstance(payload, list) or len(payload) < 2:
        raise RuntimeError(
            f"Unexpected API response for {indicator.wb_code}: {payload!r:.200}"
        )

    header, observations = payload[0], payload[1]

    if observations is None:
        raise RuntimeError(f"No data returned for {indicator.wb_code}")

    if header.get("pages", 1) > 1:
        raise RuntimeError(
            f"{indicator.wb_code} returned {header['pages']} pages; "
            "raise per_page or add pagination."
        )

    return [
        observation
        for observation in observations
        if observation.get("value") is not None
    ]


def build_dataframe(
    start_year: int = DEFAULT_START_YEAR,
    end_year: int = DEFAULT_END_YEAR,
    accessed_on: date | None = None,
) -> pd.DataFrame:
    """Fetch every curated indicator and shape it for ingestion."""
    accessed_on = accessed_on or date.today()
    records: list[dict] = []

    for indicator in INDICATORS:
        series = fetch_series(indicator, start_year, end_year)
        print(
            f"  {indicator.wb_code:<20} {len(series):3d} observations"
            f"  -> {indicator.indicator_code}"
        )

        for observation in series:
            year = int(observation["date"])

            records.append(
                {
                    "source_code": SOURCE_CODE,
                    "source_name": SOURCE_NAME,
                    "organization": ORGANIZATION,
                    "source_url": SOURCE_URL,
                    "methodology": METHODOLOGY,
                    "accessed_on": accessed_on.isoformat(),
                    "geo_code": GEO_CODE,
                    "geo_name": GEO_NAME,
                    "geo_level": GEO_LEVEL,
                    "indicator_code": indicator.indicator_code,
                    "indicator_name": indicator.indicator_name,
                    "domain": indicator.domain,
                    "indicator_unit": indicator.unit,
                    "frequency": "annual",
                    "period_start": f"{year}-01-01",
                    "period_end": f"{year}-12-31",
                    "value": observation["value"],
                    "unit": indicator.unit,
                    "observation_status": indicator.observation_status,
                    "notes": indicator.notes,
                }
            )

    if not records:
        raise RuntimeError("The API returned no observations at all.")

    frame = pd.DataFrame(records)
    return frame.sort_values(
        ["indicator_code", "period_start"]
    ).reset_index(drop=True)


def write_csv(path: str | Path, **kwargs) -> Path:
    """Fetch the curated indicators and write them as an ingestible CSV."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    frame = build_dataframe(**kwargs)
    frame.to_csv(path, index=False)

    return path


def main() -> None:
    import argparse

    from ..config import PROJECT_ROOT

    parser = argparse.ArgumentParser(
        description=(
            "Fetch Nigeria indicators from the World Bank WDI API and "
            "write them as an ingestible CSV."
        )
    )
    parser.add_argument(
        "--output",
        default=None,
        help=(
            "Where to write the CSV "
            "(default: data/raw/worldbank_wdi_<date>.csv)"
        ),
    )
    parser.add_argument(
        "--start-year", type=int, default=DEFAULT_START_YEAR
    )
    parser.add_argument(
        "--end-year", type=int, default=DEFAULT_END_YEAR
    )
    parser.add_argument(
        "--ingest",
        action="store_true",
        help="Import the fetched file after writing it",
    )
    args = parser.parse_args()

    today = date.today()
    output = args.output or (
        PROJECT_ROOT / "data" / "raw"
        / f"worldbank_wdi_{today.isoformat()}.csv"
    )

    print(f"Fetching {len(INDICATORS)} indicators for {GEO_NAME}:")
    path = write_csv(
        output,
        start_year=args.start_year,
        end_year=args.end_year,
        accessed_on=today,
    )

    frame = pd.read_csv(path)
    print(f"Wrote {len(frame)} observations to {path}")

    if args.ingest:
        from ..ingestion import ingest_csv

        batch_id, count = ingest_csv(path)
        print(f"Imported {count} observations as batch {batch_id}.")


if __name__ == "__main__":
    main()
