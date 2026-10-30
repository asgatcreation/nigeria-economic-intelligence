from sqlalchemy import inspect

from nigeria_economic_intelligence.database import engine


EXPECTED_COLUMNS = {
    "data_sources": {
        "source_id",
        "source_code",
        "source_name",
        "organization",
    },
    "geographies": {
        "geography_id",
        "geo_code",
        "geo_name",
        "geo_level",
    },
    "indicators": {
        "indicator_id",
        "indicator_code",
        "indicator_name",
        "domain",
        "frequency",
    },
    "indicator_observations": {
        "observation_id",
        "indicator_id",
        "geography_id",
        "source_id",
        "period_start",
        "period_end",
        "value",
        "metadata",
    },
}


def test_required_tables_exist():
    inspector = inspect(engine)
    assert set(EXPECTED_COLUMNS).issubset(
        set(inspector.get_table_names())
    )


def test_required_columns_exist():
    inspector = inspect(engine)

    for table, expected_columns in EXPECTED_COLUMNS.items():
        actual_columns = {
            column["name"]
            for column in inspector.get_columns(table)
        }
        assert expected_columns.issubset(actual_columns), (
            f"Missing columns in {table}: "
            f"{expected_columns - actual_columns}"
        )


def test_observations_have_foreign_keys():
    inspector = inspect(engine)

    foreign_keys = inspector.get_foreign_keys(
        "indicator_observations"
    )

    referenced_tables = {
        foreign_key["referred_table"]
        for foreign_key in foreign_keys
    }

    assert {
        "indicators",
        "geographies",
        "data_sources",
    }.issubset(referenced_tables)
