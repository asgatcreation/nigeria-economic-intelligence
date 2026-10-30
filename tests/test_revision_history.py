
from sqlalchemy import inspect, text

from nigeria_economic_intelligence.database import engine


def test_revision_table_exists():
    inspector = inspect(engine)

    assert "indicator_observation_revisions" in inspector.get_table_names()


def test_revision_trigger_exists():
    with engine.connect() as connection:
        exists = connection.execute(
            text("""
                SELECT EXISTS (
                    SELECT 1
                    FROM pg_trigger
                    WHERE tgname = 'trg_observation_revision_history'
                      AND NOT tgisinternal
                )
            """)
        ).scalar_one()

    assert exists is True


def test_revision_trigger_records_changes_and_rolls_back():
    with engine.connect() as connection:
        transaction = connection.begin()

        try:
            observation = connection.execute(
                text("""
                    SELECT observation_id, value
                    FROM indicator_observations
                    ORDER BY observation_id
                    LIMIT 1
                """)
            ).first()

            assert observation is not None
            observation_id, original_value = observation

            original_revision_count = connection.execute(
                text("""
                    SELECT COUNT(*)
                    FROM indicator_observation_revisions
                    WHERE observation_id = :observation_id
                """),
                {"observation_id": observation_id},
            ).scalar_one()

            connection.execute(
                text("""
                    UPDATE indicator_observations
                    SET value = value + 1000
                    WHERE observation_id = :observation_id
                """),
                {"observation_id": observation_id},
            )

            revision = connection.execute(
                text("""
                    SELECT previous_value, new_value
                    FROM indicator_observation_revisions
                    WHERE observation_id = :observation_id
                    ORDER BY revision_id DESC
                    LIMIT 1
                """),
                {"observation_id": observation_id},
            ).first()

            assert revision is not None
            assert revision.previous_value == original_value
            assert revision.new_value == original_value + 1000

        finally:
            transaction.rollback()

    # Confirm that the test left the database unchanged.
    with engine.connect() as connection:
        current_value = connection.execute(
            text("""
                SELECT value
                FROM indicator_observations
                WHERE observation_id = :observation_id
            """),
            {"observation_id": observation_id},
        ).scalar_one()

        current_revision_count = connection.execute(
            text("""
                SELECT COUNT(*)
                FROM indicator_observation_revisions
                WHERE observation_id = :observation_id
            """),
            {"observation_id": observation_id},
        ).scalar_one()

    assert current_value == original_value
    assert current_revision_count == original_revision_count
