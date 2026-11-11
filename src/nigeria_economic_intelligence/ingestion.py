from pathlib import Path
import hashlib
import math

import pandas as pd
from sqlalchemy import text

from .database import engine


REQUIRED_COLUMNS = {
    "source_code",
    "source_name",
    "geo_code",
    "geo_name",
    "geo_level",
    "indicator_code",
    "indicator_name",
    "domain",
    "period_start",
    "period_end",
    "value",
}

ALLOWED_GEO_LEVELS = {
    "country", "zone", "state", "lga",
    "senatorial_district", "other",
}

# Must match the indicators_domain_check constraint in the database;
# test_schema_constants reconciles the two.
ALLOWED_DOMAINS = {
    "economy", "labour_market", "demographics",
    "prices", "trade", "agriculture", "poverty", "other",
}

ALLOWED_FREQUENCIES = {
    "annual", "quarterly", "monthly",
    "weekly", "daily", "irregular",
}

ALLOWED_STATUSES = {
    "observed", "estimated", "provisional", "revised",
}

OPTIONAL_DEFAULTS = {
    "organization": None,
    "source_url": None,
    "methodology": None,
    "accessed_on": None,
    "source_notes": None,
    "indicator_unit": None,
    "indicator_description": None,
    "frequency": "irregular",
    "unit": None,
    "observation_status": "observed",
    "notes": None,
}


def validate_dataframe(data: pd.DataFrame) -> pd.DataFrame:
    """Validate and normalize indicator observations."""

    data = data.copy()
    data.columns = [str(column).strip() for column in data.columns]

    if data.columns.duplicated().any():
        raise ValueError("CSV contains duplicate column names.")

    missing = REQUIRED_COLUMNS - set(data.columns)
    if missing:
        raise ValueError(
            f"Missing required columns: {sorted(missing)}"
        )

    if data.empty:
        raise ValueError("CSV contains no observations.")

    for column, default in OPTIONAL_DEFAULTS.items():
        if column not in data.columns:
            data[column] = default

    text_columns = [
        "source_code", "source_name", "geo_code", "geo_name",
        "geo_level", "indicator_code", "indicator_name", "domain",
        "organization", "source_url", "methodology", "source_notes",
        "indicator_unit", "indicator_description", "frequency",
        "unit", "observation_status", "notes",
    ]

    for column in text_columns:
        data[column] = data[column].map(
            lambda value: (
                None if pd.isna(value) or not str(value).strip()
                else str(value).strip()
            )
        )

    required_text = [
        "source_code", "source_name", "geo_code", "geo_name",
        "geo_level", "indicator_code", "indicator_name", "domain",
    ]

    for column in required_text:
        invalid = data[column].isna()
        if invalid.any():
            rows = (data.index[invalid] + 2).tolist()
            raise ValueError(
                f"Missing values in '{column}' at CSV rows {rows}."
            )

    data["geo_level"] = data["geo_level"].str.lower()
    data["domain"] = data["domain"].str.lower()
    data["frequency"] = data["frequency"].str.lower()
    data["observation_status"] = (
        data["observation_status"].str.lower()
    )

    for column, allowed in [
        ("geo_level", ALLOWED_GEO_LEVELS),
        ("domain", ALLOWED_DOMAINS),
        ("frequency", ALLOWED_FREQUENCIES),
        ("observation_status", ALLOWED_STATUSES),
    ]:
        invalid = ~data[column].isin(allowed)
        if invalid.any():
            values = data.loc[invalid, column].unique().tolist()
            raise ValueError(
                f"Invalid value(s) for '{column}': {values}"
            )

    for column in ["period_start", "period_end"]:
        parsed = pd.to_datetime(data[column], errors="coerce")
        if parsed.isna().any():
            rows = (data.index[parsed.isna()] + 2).tolist()
            raise ValueError(
                f"Invalid dates in '{column}' at CSV rows {rows}."
            )
        data[column] = parsed.dt.date

    invalid_period = data["period_end"] < data["period_start"]
    if invalid_period.any():
        rows = (data.index[invalid_period] + 2).tolist()
        raise ValueError(
            f"Period end precedes period start at CSV rows {rows}."
        )

    numeric = pd.to_numeric(data["value"], errors="coerce")
    invalid_numeric = numeric.isna()
    if invalid_numeric.any():
        rows = (data.index[invalid_numeric] + 2).tolist()
        raise ValueError(
            f"Missing or invalid numeric values at CSV rows {rows}."
        )

    if not numeric.map(math.isfinite).all():
        raise ValueError("Values must be finite numbers.")

    data["value"] = numeric

    if data["accessed_on"].notna().any():
        accessed = pd.to_datetime(
            data["accessed_on"], errors="coerce"
        )
        invalid = data["accessed_on"].notna() & accessed.isna()
        if invalid.any():
            raise ValueError("Invalid dates in 'accessed_on'.")
        data["accessed_on"] = accessed.dt.date.where(
            accessed.notna(), None
        )

    duplicate_key = [
        "indicator_code", "geo_code", "source_code",
        "period_start", "period_end",
    ]
    duplicates = data.duplicated(duplicate_key, keep=False)
    if duplicates.any():
        rows = (data.index[duplicates] + 2).tolist()
        raise ValueError(
            f"Duplicate observations at CSV rows {rows}."
        )

    return data


def validate_csv(path: str | Path) -> pd.DataFrame:
    """Read a CSV and return validated observations."""
    path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(f"CSV file not found: {path}")

    data = pd.read_csv(path)
    return validate_dataframe(data)


def _file_sha256(path: Path) -> str:
    """Return the SHA-256 digest of a file, read in chunks."""
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def _upsert_id(connection, query: str, parameters: dict) -> int:
    result = connection.execute(text(query), parameters)
    return result.scalar_one()


def _open_batch(path: Path, rows_received: int) -> int:
    """Record the start of an import and return its batch id."""
    with engine.begin() as connection:
        return _upsert_id(
            connection,
            """
            INSERT INTO data_import_batches
                (original_filename, file_sha256, rows_received)
            VALUES
                (:original_filename, :file_sha256, :rows_received)
            RETURNING batch_id
            """,
            {
                "original_filename": path.name,
                "file_sha256": _file_sha256(path),
                "rows_received": rows_received,
            },
        )


def _close_batch(
    batch_id: int,
    status: str,
    *,
    rows_processed: int = 0,
    rows_rejected: int = 0,
    source_id: int | None = None,
    error_message: str | None = None,
) -> None:
    """Mark an import batch as completed or failed."""
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                UPDATE data_import_batches
                SET status = :status,
                    rows_processed = :rows_processed,
                    rows_rejected = :rows_rejected,
                    source_id = :source_id,
                    error_message = :error_message,
                    completed_at = CURRENT_TIMESTAMP
                WHERE batch_id = :batch_id
                """
            ),
            {
                "batch_id": batch_id,
                "status": status,
                "rows_processed": rows_processed,
                "rows_rejected": rows_rejected,
                "source_id": source_id,
                "error_message": error_message,
            },
        )


def _upsert_sources(connection, data: pd.DataFrame) -> dict[str, int]:
    """Upsert each distinct source once and map its code to its id."""
    columns = [
        "source_code", "source_name", "organization",
        "source_url", "methodology", "accessed_on", "source_notes",
    ]
    distinct = data[columns].drop_duplicates("source_code")

    return {
        row["source_code"]: _upsert_id(
            connection,
            """
            INSERT INTO data_sources
                (source_code, source_name, organization,
                 source_url, methodology, accessed_on, notes)
            VALUES
                (:source_code, :source_name, :organization,
                 :source_url, :methodology, :accessed_on,
                 :source_notes)
            ON CONFLICT (source_code) DO UPDATE SET
                source_name = EXCLUDED.source_name,
                organization = EXCLUDED.organization,
                source_url = EXCLUDED.source_url,
                methodology = EXCLUDED.methodology,
                accessed_on = EXCLUDED.accessed_on,
                notes = EXCLUDED.notes
            RETURNING source_id
            """,
            row,
        )
        for row in distinct.to_dict(orient="records")
    }


def _upsert_geographies(connection, data: pd.DataFrame) -> dict[str, int]:
    """Upsert each distinct geography once and map its code to its id."""
    columns = ["geo_code", "geo_name", "geo_level"]
    distinct = data[columns].drop_duplicates("geo_code")

    return {
        row["geo_code"]: _upsert_id(
            connection,
            """
            INSERT INTO geographies
                (geo_code, geo_name, geo_level)
            VALUES (:geo_code, :geo_name, :geo_level)
            ON CONFLICT (geo_code) DO UPDATE SET
                geo_name = EXCLUDED.geo_name,
                geo_level = EXCLUDED.geo_level
            RETURNING geography_id
            """,
            row,
        )
        for row in distinct.to_dict(orient="records")
    }


def _upsert_indicators(connection, data: pd.DataFrame) -> dict[str, int]:
    """Upsert each distinct indicator once and map its code to its id."""
    columns = [
        "indicator_code", "indicator_name", "domain",
        "indicator_unit", "indicator_description", "frequency",
    ]
    distinct = data[columns].drop_duplicates("indicator_code")

    return {
        row["indicator_code"]: _upsert_id(
            connection,
            """
            INSERT INTO indicators
                (indicator_code, indicator_name, domain,
                 unit, description, frequency)
            VALUES
                (:indicator_code, :indicator_name, :domain,
                 :indicator_unit, :indicator_description,
                 :frequency)
            ON CONFLICT (indicator_code) DO UPDATE SET
                indicator_name = EXCLUDED.indicator_name,
                domain = EXCLUDED.domain,
                unit = EXCLUDED.unit,
                description = EXCLUDED.description,
                frequency = EXCLUDED.frequency
            RETURNING indicator_id
            """,
            row,
        )
        for row in distinct.to_dict(orient="records")
    }


def _load_observations(data: pd.DataFrame, batch_id: int) -> int:
    """Upsert validated observations inside a single transaction."""
    with engine.begin() as connection:
        # Transaction-local, so the revision trigger can attribute every
        # change it records to this import batch.
        connection.execute(
            text("SELECT set_config('app.import_batch_id', :value, true)"),
            {"value": str(batch_id)},
        )

        source_ids = _upsert_sources(connection, data)
        geography_ids = _upsert_geographies(connection, data)
        indicator_ids = _upsert_indicators(connection, data)

        rows = [
            {
                **row,
                "indicator_id": indicator_ids[row["indicator_code"]],
                "geography_id": geography_ids[row["geo_code"]],
                "source_id": source_ids[row["source_code"]],
                "last_import_batch_id": batch_id,
            }
            for row in data.to_dict(orient="records")
        ]

        connection.execute(
            text(
                """
                INSERT INTO indicator_observations
                    (indicator_id, geography_id, source_id,
                     period_start, period_end, value, unit,
                     observation_status, notes, last_import_batch_id)
                VALUES
                    (:indicator_id, :geography_id, :source_id,
                     :period_start, :period_end, :value, :unit,
                     :observation_status, :notes, :last_import_batch_id)
                ON CONFLICT
                    (indicator_id, geography_id, source_id,
                     period_start, period_end)
                DO UPDATE SET
                    value = EXCLUDED.value,
                    unit = EXCLUDED.unit,
                    observation_status = EXCLUDED.observation_status,
                    notes = EXCLUDED.notes,
                    last_import_batch_id = EXCLUDED.last_import_batch_id
                """
            ),
            rows,
        )

        return len(rows)


def _resolve_batch_source(data: pd.DataFrame) -> int | None:
    """Return the source id when a file carries exactly one source."""
    source_codes = data["source_code"].unique().tolist()

    if len(source_codes) != 1:
        return None

    with engine.connect() as connection:
        return connection.execute(
            text(
                "SELECT source_id FROM data_sources "
                "WHERE source_code = :source_code"
            ),
            {"source_code": source_codes[0]},
        ).scalar_one()


def ingest_csv(path: str | Path) -> tuple[int, int]:
    """Import a CSV as a tracked batch.

    Returns the batch id and the number of observations processed. The
    batch is recorded whether the import succeeds or fails, so a
    rejected file still leaves an audit trail.
    """
    path = Path(path)

    if not path.is_file():
        raise FileNotFoundError(f"CSV file not found: {path}")

    raw = pd.read_csv(path)
    batch_id = _open_batch(path, len(raw))

    try:
        data = validate_dataframe(raw)
        imported = _load_observations(data, batch_id)

    except Exception as exc:
        _close_batch(
            batch_id,
            "failed",
            rows_rejected=len(raw),
            error_message=str(exc),
        )
        raise

    _close_batch(
        batch_id,
        "completed",
        rows_processed=imported,
        source_id=_resolve_batch_source(data),
    )

    return batch_id, imported


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Validate and import indicator observations."
    )
    parser.add_argument("csv_file", help="Path to the input CSV")
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate the file without changing the database",
    )
    args = parser.parse_args()

    try:
        if args.validate_only:
            data = validate_csv(args.csv_file)
            print(f"Validation successful: {len(data)} observations.")
            print("No actual economic data has been assumed or generated.")
            return

        batch_id, count = ingest_csv(args.csv_file)

    except (ValueError, FileNotFoundError) as exc:
        raise SystemExit(f"Import rejected: {exc}") from exc

    print(f"Import successful: {count} observations processed.")
    print(f"Import batch id: {batch_id}")


if __name__ == "__main__":
    main()
