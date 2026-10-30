from sqlalchemy import inspect, text

from nigeria_economic_intelligence import migrate
from nigeria_economic_intelligence.database import engine


def test_ledger_table_exists():
    migrate._ensure_ledger()

    assert "schema_migrations" in inspect(engine).get_table_names()


def test_every_migration_file_is_recorded_as_applied():
    migrate._ensure_ledger()
    applied = migrate._applied()

    for path in migrate._migration_files():
        assert path.name in applied, f"{path.name} has not been applied"


def test_recorded_checksums_match_the_files_on_disk():
    migrate._ensure_ledger()
    applied = migrate._applied()

    for path in migrate._migration_files():
        sql = path.read_text(encoding="utf-8")
        assert not migrate._drifted(applied, path, sql), (
            f"{path.name} changed after it was applied"
        )


def test_upgrade_is_a_no_op_when_up_to_date():
    assert migrate.upgrade() == 0


def test_batch_tracking_columns_exist():
    inspector = inspect(engine)

    observation_columns = {
        column["name"]
        for column in inspector.get_columns("indicator_observations")
    }
    revision_columns = {
        column["name"]
        for column in inspector.get_columns(
            "indicator_observation_revisions"
        )
    }

    assert "last_import_batch_id" in observation_columns
    assert "batch_id" in revision_columns


def test_revision_trigger_tolerates_an_unset_batch_id():
    """A manual update outside an import must still record a revision."""
    with engine.connect() as connection:
        transaction = connection.begin()

        try:
            observation = connection.execute(
                text(
                    """
                    SELECT observation_id
                    FROM indicator_observations
                    ORDER BY observation_id
                    LIMIT 1
                    """
                )
            ).first()

            assert observation is not None
            observation_id = observation.observation_id

            connection.execute(
                text(
                    """
                    UPDATE indicator_observations
                    SET notes = 'manual edit under test'
                    WHERE observation_id = :observation_id
                    """
                ),
                {"observation_id": observation_id},
            )

            revision = connection.execute(
                text(
                    """
                    SELECT batch_id
                    FROM indicator_observation_revisions
                    WHERE observation_id = :observation_id
                    ORDER BY revision_id DESC
                    LIMIT 1
                    """
                ),
                {"observation_id": observation_id},
            ).first()

            assert revision is not None
            assert revision.batch_id is None

        finally:
            transaction.rollback()
