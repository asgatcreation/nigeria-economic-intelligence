
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


def test_revision_trigger_records_changes_and_rolls_back(scratch_observation):
    connection = scratch_observation["connection"]
    observation_id = scratch_observation["observation_id"]
    original_value = scratch_observation["value"]

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


def test_the_revision_test_leaves_nothing_behind():
    """The rollback must take the fixture row and its revision with it.

    Without this the trigger test could pass while quietly writing to the
    warehouse, which is the one thing a revision-history test must not do.
    """
    with engine.connect() as connection:
        leftovers = connection.execute(
            text("""
                SELECT COUNT(*)
                FROM indicator_observations AS o
                JOIN indicators AS i
                  ON i.indicator_id = o.indicator_id
                WHERE i.indicator_code = 'TEST_INDICATOR'
            """)
        ).scalar_one()

        orphan_revisions = connection.execute(
            text("""
                SELECT COUNT(*)
                FROM indicator_observation_revisions AS r
                LEFT JOIN indicator_observations AS o
                  ON o.observation_id = r.observation_id
                WHERE o.observation_id IS NULL
            """)
        ).scalar_one()

    assert leftovers == 0
    assert orphan_revisions == 0
