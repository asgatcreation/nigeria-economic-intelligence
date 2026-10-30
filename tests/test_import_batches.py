import pandas as pd
import pytest
from sqlalchemy import text

from nigeria_economic_intelligence.database import engine
from nigeria_economic_intelligence.ingestion import ingest_csv


SOURCE_CODE = "PYTEST_BATCH_SOURCE"
GEO_CODE = "NG-PYTEST-BATCH"
INDICATOR_CODE = "PYTEST_BATCH_INDICATOR"


def _observation_row(period_start, period_end, value):
    return {
        "source_code": SOURCE_CODE,
        "source_name": "Pytest batch source",
        "organization": "Internal test",
        "geo_code": GEO_CODE,
        "geo_name": "Pytest batch geography",
        "geo_level": "other",
        "indicator_code": INDICATOR_CODE,
        "indicator_name": "Pytest batch indicator",
        "domain": "prices",
        "indicator_unit": "percent",
        "frequency": "monthly",
        "period_start": period_start,
        "period_end": period_end,
        "value": value,
        "observation_status": "observed",
        "notes": "Fictional value for pipeline testing only",
    }


def _write_csv(tmp_path, rows, filename="observations.csv"):
    path = tmp_path / filename
    pd.DataFrame(rows).to_csv(path, index=False)
    return path


def _batch(batch_id):
    with engine.connect() as connection:
        return connection.execute(
            text(
                """
                SELECT status, rows_received, rows_processed,
                       rows_rejected, source_id, completed_at,
                       error_message, file_sha256, original_filename
                FROM data_import_batches
                WHERE batch_id = :batch_id
                """
            ),
            {"batch_id": batch_id},
        ).one()


@pytest.fixture
def clean_test_records():
    """Remove this module's fixture records before and after each test."""

    def cleanup():
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    DELETE FROM indicator_observation_revisions
                    WHERE observation_id IN (
                        SELECT o.observation_id
                        FROM indicator_observations AS o
                        JOIN indicators AS i
                          ON i.indicator_id = o.indicator_id
                        WHERE i.indicator_code = :indicator_code
                    )
                    """
                ),
                {"indicator_code": INDICATOR_CODE},
            )
            connection.execute(
                text(
                    """
                    DELETE FROM indicator_observations
                    WHERE indicator_id IN (
                        SELECT indicator_id FROM indicators
                        WHERE indicator_code = :indicator_code
                    )
                    """
                ),
                {"indicator_code": INDICATOR_CODE},
            )
            connection.execute(
                text(
                    "DELETE FROM indicators "
                    "WHERE indicator_code = :indicator_code"
                ),
                {"indicator_code": INDICATOR_CODE},
            )
            connection.execute(
                text("DELETE FROM geographies WHERE geo_code = :geo_code"),
                {"geo_code": GEO_CODE},
            )
            connection.execute(
                text(
                    """
                    DELETE FROM data_import_batches
                    WHERE source_id IN (
                        SELECT source_id FROM data_sources
                        WHERE source_code = :source_code
                    )
                    """
                ),
                {"source_code": SOURCE_CODE},
            )
            connection.execute(
                text(
                    "DELETE FROM data_sources "
                    "WHERE source_code = :source_code"
                ),
                {"source_code": SOURCE_CODE},
            )

    cleanup()
    yield
    cleanup()


def test_successful_import_records_a_completed_batch(
    tmp_path, clean_test_records
):
    path = _write_csv(
        tmp_path,
        [
            _observation_row("2026-01-01", "2026-01-31", 10.0),
            _observation_row("2026-02-01", "2026-02-28", 11.0),
        ],
    )

    batch_id, imported = ingest_csv(path)

    assert imported == 2

    batch = _batch(batch_id)

    assert batch.status == "completed"
    assert batch.rows_received == 2
    assert batch.rows_processed == 2
    assert batch.rows_rejected == 0
    assert batch.completed_at is not None
    assert batch.error_message is None
    assert batch.original_filename == "observations.csv"
    assert len(batch.file_sha256) == 64
    assert batch.source_id is not None


def test_imported_observations_reference_their_batch(
    tmp_path, clean_test_records
):
    path = _write_csv(
        tmp_path,
        [_observation_row("2026-03-01", "2026-03-31", 12.0)],
    )

    batch_id, _ = ingest_csv(path)

    with engine.connect() as connection:
        batch_ids = connection.execute(
            text(
                """
                SELECT DISTINCT o.last_import_batch_id
                FROM indicator_observations AS o
                JOIN indicators AS i
                  ON i.indicator_id = o.indicator_id
                WHERE i.indicator_code = :indicator_code
                """
            ),
            {"indicator_code": INDICATOR_CODE},
        ).scalars().all()

    assert batch_ids == [batch_id]


def test_reimport_attributes_the_revision_to_the_new_batch(
    tmp_path, clean_test_records
):
    first = _write_csv(
        tmp_path,
        [_observation_row("2026-04-01", "2026-04-30", 20.0)],
        filename="first.csv",
    )
    second = _write_csv(
        tmp_path,
        [_observation_row("2026-04-01", "2026-04-30", 25.0)],
        filename="second.csv",
    )

    first_batch_id, _ = ingest_csv(first)
    second_batch_id, _ = ingest_csv(second)

    assert second_batch_id != first_batch_id

    with engine.connect() as connection:
        revision = connection.execute(
            text(
                """
                SELECT r.previous_value, r.new_value, r.batch_id
                FROM indicator_observation_revisions AS r
                JOIN indicator_observations AS o
                  ON o.observation_id = r.observation_id
                JOIN indicators AS i
                  ON i.indicator_id = o.indicator_id
                WHERE i.indicator_code = :indicator_code
                ORDER BY r.revision_id DESC
                LIMIT 1
                """
            ),
            {"indicator_code": INDICATOR_CODE},
        ).one()

    assert revision.previous_value == 20
    assert revision.new_value == 25
    assert revision.batch_id == second_batch_id


def test_rejected_file_records_a_failed_batch(tmp_path, clean_test_records):
    row = _observation_row("2026-05-01", "2026-05-31", 30.0)
    row["geo_level"] = "province"
    path = _write_csv(tmp_path, [row], filename="invalid.csv")

    with pytest.raises(ValueError, match="geo_level"):
        ingest_csv(path)

    with engine.connect() as connection:
        batch = connection.execute(
            text(
                """
                SELECT status, rows_received, rows_processed,
                       rows_rejected, error_message
                FROM data_import_batches
                WHERE original_filename = 'invalid.csv'
                ORDER BY batch_id DESC
                LIMIT 1
                """
            )
        ).one()

    assert batch.status == "failed"
    assert batch.rows_received == 1
    assert batch.rows_processed == 0
    assert batch.rows_rejected == 1
    assert "geo_level" in batch.error_message

    # Nothing from the rejected file reached the warehouse.
    with engine.connect() as connection:
        count = connection.execute(
            text(
                "SELECT COUNT(*) FROM indicators "
                "WHERE indicator_code = :indicator_code"
            ),
            {"indicator_code": INDICATOR_CODE},
        ).scalar_one()

    assert count == 0

    with engine.begin() as connection:
        connection.execute(
            text(
                "DELETE FROM data_import_batches "
                "WHERE original_filename = 'invalid.csv'"
            )
        )


def test_missing_file_raises_before_any_batch_is_opened(
    tmp_path, clean_test_records
):
    with engine.connect() as connection:
        before = connection.execute(
            text("SELECT COUNT(*) FROM data_import_batches")
        ).scalar_one()

    with pytest.raises(FileNotFoundError):
        ingest_csv(tmp_path / "does_not_exist.csv")

    with engine.connect() as connection:
        after = connection.execute(
            text("SELECT COUNT(*) FROM data_import_batches")
        ).scalar_one()

    assert after == before
