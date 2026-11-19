"""Nigeria state boundaries from the Common Operational Dataset (COD-AB).

Published by OCHA on the Humanitarian Data Exchange under CC BY-IGO 3.0,
keyed on the same ADM1 P-codes as the population and poverty data already
in the warehouse, which is the reason to prefer it over geoBoundaries or
GADM: the join needs no name matching and therefore cannot quietly go
wrong on "Nasarawa" against "Nassarawa".

Two different things come out of this file, and they are treated
differently on purpose.

*Land area* is a measurement of a state and goes into the warehouse
through the ordinary validated, batch-tracked import path, like every
other observation.

*Geometry* does not. The schema stores indicator observations -- a
number for an indicator, a place and a period -- and a polygon is none
of those. Rather than bend the schema to hold a shape, the boundaries
stay a reference artefact: downloaded, checksummed, cached, and read
directly by the mapping and spatial-weights code. The provenance still
travels with it, because the archive's SHA-256 is recorded here and
reported by the CLI.

A caveat that belongs with the areas. The published state areas sum to
about 910,000 km2 against the roughly 923,800 km2 usually quoted for
Nigeria -- a 1.5% shortfall, which is what boundary generalisation and
the treatment of water bodies produce. The areas are internally
consistent, so densities computed from them are comparable between
states; they should not be quoted as authoritative national land area.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen
import hashlib
import json
import zipfile

import pandas as pd

DATASET_PAGE = "https://data.humdata.org/dataset/cod-ab-nga"
ARCHIVE_URL = (
    "https://data.humdata.org/dataset/"
    "81ac1d38-f603-4a98-804d-325c658599a3/resource/"
    "7e30ec96-7f29-4ee8-9f4c-77633b353cbb/download/"
    "nga_admin_boundaries.geojson.zip"
)
ADMIN1_MEMBER = "nga_admin1.geojson"

SOURCE_CODE = "HDX_COD_AB_NGA"
SOURCE_NAME = "Nigeria subnational administrative boundaries (COD-AB)"
ORGANIZATION = "OCHA Field Information Services Section (FISS)"
LICENCE = (
    "Creative Commons Attribution for Intergovernmental Organisations "
    "(CC BY-IGO 3.0)"
)
METHODOLOGY = (
    "Common Operational Dataset for administrative boundaries (COD-AB), "
    "Nigeria, admin level 1, published via the Humanitarian Data "
    "Exchange by OCHA. Boundaries valid on 2019-04-17, version v01, "
    "licensed CC BY-IGO 3.0. Land area is the published area_sqkm "
    "attribute of each state polygon. State areas sum to roughly 1.5% "
    "below the national land area usually quoted for Nigeria, a "
    "difference attributable to boundary generalisation; they are "
    "internally consistent and so comparable between states."
)

REFERENCE_YEAR = 2019
GEO_LEVEL = "state"
EXPECTED_STATES = 37

AREA_INDICATOR = "NGA_STATE_AREA"
AREA_NAME = "State land area"
AREA_UNIT = "square kilometres"
AREA_DESCRIPTION = (
    "Land area of the state in square kilometres, as published in the "
    "COD-AB admin level 1 boundary file (area_sqkm attribute)."
)
AREA_NOTE = (
    "Derived from generalised boundary polygons; comparable between "
    "states, not authoritative national land area."
)

# Nigeria's land area as usually published, used only as a sanity bound.
NATIONAL_AREA_SQKM = 923_768.0
AREA_TOLERANCE = 0.05

_DEFAULT_CACHE = Path("data") / "raw" / "cod_ab_nga"


@dataclass(frozen=True)
class StateBoundary:
    """One state's published boundary and its attributes."""

    pcode: str
    name: str
    area_sqkm: float
    centre_lat: float
    centre_lon: float
    polygons: tuple[tuple[tuple[float, float], ...], ...]

    @property
    def centre(self) -> tuple[float, float]:
        return (self.centre_lat, self.centre_lon)


def archive_path(cache_dir: str | Path | None = None) -> Path:
    from ..config import PROJECT_ROOT

    base = Path(cache_dir) if cache_dir else PROJECT_ROOT / _DEFAULT_CACHE
    return base / "nga_admin_boundaries.geojson.zip"


def fetch_archive(
    path: str | Path | None = None,
    *,
    refresh: bool = False,
) -> Path:
    """Return a local copy of the boundary archive, downloading if needed.

    The file is about 11 MB and does not change between releases, so it
    is cached rather than re-fetched. `refresh` forces a download.
    """
    if path is not None:
        local = Path(path)
        if not local.exists():
            raise FileNotFoundError(f"No boundary archive at {local}")
        return local

    local = archive_path()
    if local.exists() and not refresh:
        return local

    local.parent.mkdir(parents=True, exist_ok=True)
    request = Request(ARCHIVE_URL, headers={"User-Agent": "nei-connector"})
    with urlopen(request, timeout=300) as response:
        payload = response.read()

    local.write_bytes(payload)
    return local


def archive_digest(path: str | Path) -> str:
    """SHA-256 of the archive, so a figure can cite the file it used."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _rings(geometry: dict) -> tuple[tuple[tuple[float, float], ...], ...]:
    """Flatten a Polygon or MultiPolygon to its outer rings.

    Interior rings are dropped: no Nigerian state is a doughnut, and
    carrying holes would complicate the drawing code for nothing.
    """
    kind = geometry.get("type")
    coordinates = geometry.get("coordinates")

    if kind == "Polygon":
        parts = [coordinates]
    elif kind == "MultiPolygon":
        parts = list(coordinates)
    else:
        raise RuntimeError(f"Unsupported boundary geometry: {kind!r}")

    rings = []
    for part in parts:
        if not part:
            raise RuntimeError("Boundary polygon with no outer ring")
        outer = tuple((float(x), float(y)) for x, y in part[0])
        if len(outer) < 4:
            raise RuntimeError("Boundary ring with fewer than four points")
        rings.append(outer)

    return tuple(rings)


def load_admin1(
    path: str | Path | None = None,
) -> list[StateBoundary]:
    """Read the 37 state boundaries from the archive, with checks."""
    archive = fetch_archive(path)

    with zipfile.ZipFile(archive) as bundle:
        names = set(bundle.namelist())
        if ADMIN1_MEMBER not in names:
            raise RuntimeError(
                f"{archive} has no {ADMIN1_MEMBER}; found {sorted(names)}"
            )
        collection = json.loads(bundle.read(ADMIN1_MEMBER).decode("utf-8"))

    features = collection.get("features") or []
    if len(features) != EXPECTED_STATES:
        raise RuntimeError(
            f"Expected {EXPECTED_STATES} states in {ADMIN1_MEMBER}, "
            f"found {len(features)}. Refusing to guess which is missing."
        )

    boundaries = []
    for feature in features:
        properties = feature.get("properties") or {}
        pcode = (properties.get("adm1_pcode") or "").strip()
        name = (properties.get("adm1_name") or "").strip()

        if not pcode or not name:
            raise RuntimeError(
                f"Boundary feature with no P-code or name: {properties!r:.160}"
            )

        for field in ("area_sqkm", "center_lat", "center_lon"):
            if properties.get(field) is None:
                raise RuntimeError(f"{pcode} has no {field}")

        boundaries.append(
            StateBoundary(
                pcode=pcode,
                name=name,
                area_sqkm=float(properties["area_sqkm"]),
                centre_lat=float(properties["center_lat"]),
                centre_lon=float(properties["center_lon"]),
                polygons=_rings(feature.get("geometry") or {}),
            )
        )

    codes = {boundary.pcode for boundary in boundaries}
    if len(codes) != EXPECTED_STATES:
        duplicated = sorted(
            code for code in codes
            if sum(b.pcode == code for b in boundaries) > 1
        )
        raise RuntimeError(f"Duplicate state P-codes: {duplicated}")

    total = sum(boundary.area_sqkm for boundary in boundaries)
    shortfall = abs(total - NATIONAL_AREA_SQKM) / NATIONAL_AREA_SQKM
    if shortfall > AREA_TOLERANCE:
        raise RuntimeError(
            f"State areas sum to {total:,.0f} km2, which is "
            f"{shortfall:.1%} from the published national area of "
            f"{NATIONAL_AREA_SQKM:,.0f} km2. That is outside the "
            f"{AREA_TOLERANCE:.0%} tolerance, so the file is not what "
            "this connector expects."
        )

    return sorted(boundaries, key=lambda boundary: boundary.pcode)


def build_dataframe(path: str | Path | None = None) -> pd.DataFrame:
    """Shape the published state areas for ingestion.

    Only the areas: the geometry is not an indicator observation and is
    read straight from the archive by the mapping code instead.
    """
    records = [
        {
            "source_code": SOURCE_CODE,
            "source_name": SOURCE_NAME,
            "organization": ORGANIZATION,
            "source_url": DATASET_PAGE,
            "methodology": METHODOLOGY,
            "geo_code": boundary.pcode,
            "geo_name": boundary.name,
            "geo_level": GEO_LEVEL,
            "indicator_code": AREA_INDICATOR,
            "indicator_name": AREA_NAME,
            "domain": "geography",
            "indicator_unit": AREA_UNIT,
            "indicator_description": AREA_DESCRIPTION,
            "frequency": "irregular",
            "period_start": f"{REFERENCE_YEAR}-01-01",
            "period_end": f"{REFERENCE_YEAR}-12-31",
            "value": round(boundary.area_sqkm, 4),
            "unit": AREA_UNIT,
            "observation_status": "observed",
            "notes": AREA_NOTE,
        }
        for boundary in load_admin1(path)
    ]

    return pd.DataFrame(records).sort_values("geo_code").reset_index(drop=True)


def write_csv(output: str | Path, path: str | Path | None = None) -> Path:
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
            "Fetch Nigeria state boundaries from HDX and write the "
            "published land areas as an ingestible CSV."
        )
    )
    parser.add_argument("--source-file", default=None)
    parser.add_argument("--output", default=None)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Re-download the archive even if it is already cached",
    )
    parser.add_argument("--ingest", action="store_true")
    args = parser.parse_args()

    archive = fetch_archive(args.source_file, refresh=args.refresh)
    print("Nigeria state boundaries (COD-AB, OCHA via HDX)")
    print(f"  licence: {LICENCE}")
    print(f"  archive: {archive}")
    print(f"  sha256:  {archive_digest(archive)}")

    boundaries = load_admin1(archive)
    total = sum(boundary.area_sqkm for boundary in boundaries)
    print(
        f"  {len(boundaries)} states, {total:,.0f} km2 total "
        f"({total / NATIONAL_AREA_SQKM - 1:+.1%} against the published "
        "national area)"
    )

    output = args.output or (
        PROJECT_ROOT / "data" / "raw"
        / f"cod_ab_state_area_{date.today().isoformat()}.csv"
    )
    path = write_csv(output, archive)
    print(f"Wrote {path}")

    if args.ingest:
        from ..ingestion import ingest_csv

        batch_id, count = ingest_csv(path)
        print(f"Imported {count} observations as batch {batch_id}.")


if __name__ == "__main__":
    main()
