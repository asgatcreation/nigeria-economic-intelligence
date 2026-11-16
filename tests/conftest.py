"""Shared fixtures.

The trigger tests used to pick whichever observation happened to be first
in the table and mutate it inside a rolled-back transaction. That worked
on a loaded warehouse and failed on an empty one, which made the tests
depend on an import having been run rather than on the schema they were
written to check — CI, which applies the migrations to a clean database,
found it immediately.

They now build their own row inside the same rolled-back transaction, so
they test the trigger against a value whose before-and-after state is
known, and run against a database that has nothing in it but the schema.
"""

import pytest
from sqlalchemy import text

from nigeria_economic_intelligence.database import engine


@pytest.fixture
def rolled_back_connection():
    """A connection in a transaction that is always rolled back."""
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            transaction.rollback()


@pytest.fixture
def scratch_observation(rolled_back_connection):
    """Insert one observation and return its id and value.

    Everything it needs is created here, except the geography, which
    migration 004 seeds and every database therefore has.
    """
    connection = rolled_back_connection

    source_id = connection.execute(
        text(
            """
            INSERT INTO data_sources (source_code, source_name, organization)
            VALUES ('TEST_SRC', 'Fixture source', 'pytest')
            RETURNING source_id
            """
        )
    ).scalar_one()

    indicator_id = connection.execute(
        text(
            """
            INSERT INTO indicators
                (indicator_code, indicator_name, domain, unit, frequency)
            VALUES
                ('TEST_INDICATOR', 'Fixture indicator', 'economy',
                 'index', 'annual')
            RETURNING indicator_id
            """
        )
    ).scalar_one()

    geography_id = connection.execute(
        text("SELECT geography_id FROM geographies WHERE geo_code = 'NGA'")
    ).scalar_one()

    value = 100
    observation_id = connection.execute(
        text(
            """
            INSERT INTO indicator_observations
                (indicator_id, geography_id, source_id,
                 period_start, period_end, value, observation_status)
            VALUES
                (:indicator_id, :geography_id, :source_id,
                 DATE '2020-01-01', DATE '2020-12-31', :value, 'observed')
            RETURNING observation_id
            """
        ),
        {
            "indicator_id": indicator_id,
            "geography_id": geography_id,
            "source_id": source_id,
            "value": value,
        },
    ).scalar_one()

    return {
        "connection": connection,
        "observation_id": observation_id,
        "value": value,
    }
