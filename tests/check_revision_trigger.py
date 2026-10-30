
from sqlalchemy import text

from nigeria_economic_intelligence.database import engine


def main():
    with engine.connect() as connection:
        transaction = connection.begin()

        try:
            observation = connection.execute(
                text("""
                    SELECT o.observation_id, o.value
                    FROM indicator_observations AS o
                    JOIN indicators AS i
                      ON i.indicator_id = o.indicator_id
                    WHERE i.indicator_code = 'DEMO_INFLATION'
                      AND o.period_start = DATE '2026-01-01'
                """)
            ).first()

            if observation is None:
                raise RuntimeError(
                    "Demo observation not found. No test was performed."
                )

            observation_id, original_value = observation

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

            if revision is None:
                raise RuntimeError(
                    "The update occurred, but no revision was recorded."
                )

            print("Original value:", original_value)
            print("Recorded previous value:", revision.previous_value)
            print("Recorded new value:", revision.new_value)
            print("Revision trigger test: PASSED")

        finally:
            transaction.rollback()
            print("Test transaction rolled back.")

    with engine.connect() as connection:
        current_value = connection.execute(
            text("""
                SELECT o.value
                FROM indicator_observations AS o
                JOIN indicators AS i
                  ON i.indicator_id = o.indicator_id
                WHERE i.indicator_code = 'DEMO_INFLATION'
                  AND o.period_start = DATE '2026-01-01'
            """)
        ).scalar_one()

        print("Value after rollback:", current_value)


if __name__ == "__main__":
    main()
