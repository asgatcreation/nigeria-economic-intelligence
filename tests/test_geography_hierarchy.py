"""Tests for the seeded Nigeria geography hierarchy (migration 004)."""

from sqlalchemy import text

from nigeria_economic_intelligence.database import engine

EXPECTED_ZONE_SIZES = {
    "North Central": 7,  # includes the Federal Capital Territory
    "North East": 6,
    "North West": 7,
    "South East": 5,
    "South South": 6,
    "South West": 6,
}


def _query(sql: str, **parameters):
    with engine.connect() as connection:
        return connection.execute(text(sql), parameters).all()


def test_all_thirty_seven_states_exist():
    rows = _query(
        "SELECT count(*) FROM geographies WHERE geo_level = 'state'"
    )

    # 36 states plus the Federal Capital Territory.
    assert rows[0][0] == 37


def test_every_state_has_a_zone_parent():
    orphans = _query(
        """
        SELECT geo_code, geo_name
        FROM geographies
        WHERE geo_level = 'state' AND parent_id IS NULL
        """
    )

    assert orphans == [], f"states with no zone: {orphans}"


def test_zone_membership_matches_the_official_split():
    rows = _query(
        """
        SELECT z.geo_name, count(s.geography_id)
        FROM geographies AS z
        LEFT JOIN geographies AS s
          ON s.parent_id = z.geography_id
        WHERE z.geo_level = 'zone'
        GROUP BY z.geo_name
        """
    )

    assert dict(rows) == EXPECTED_ZONE_SIZES


def test_zones_hang_off_the_country():
    rows = _query(
        """
        SELECT count(*)
        FROM geographies AS z
        JOIN geographies AS c
          ON c.geography_id = z.parent_id
        WHERE z.geo_level = 'zone' AND c.geo_code = 'NGA'
        """
    )

    assert rows[0][0] == 6


def test_state_codes_are_the_published_pcodes():
    rows = _query(
        """
        SELECT geo_code FROM geographies
        WHERE geo_level = 'state'
        ORDER BY geo_code
        """
    )
    codes = [row[0] for row in rows]

    assert codes == [f"NG{number:03d}" for number in range(1, 38)]


def test_the_hierarchy_has_no_cycles():
    """A geography must never be its own ancestor."""
    rows = _query(
        """
        WITH RECURSIVE walk AS (
            SELECT geography_id, parent_id, 1 AS depth
            FROM geographies
            UNION ALL
            SELECT w.geography_id, g.parent_id, w.depth + 1
            FROM walk AS w
            JOIN geographies AS g
              ON g.geography_id = w.parent_id
            WHERE w.depth < 10
        )
        SELECT count(*) FROM walk
        WHERE geography_id = parent_id OR depth >= 10
        """
    )

    assert rows[0][0] == 0


def test_an_import_does_not_detach_a_state_from_its_zone():
    """The ingestion upsert must not clobber parent_id.

    Imports supply only code, name and level, so a careless upsert would
    null the parent and silently flatten the hierarchy.
    """
    before = _query(
        """
        SELECT parent_id FROM geographies WHERE geo_code = 'NG025'
        """
    )[0][0]

    assert before is not None

    with engine.begin() as connection:
        connection.execute(
            text(
                """
                INSERT INTO geographies (geo_code, geo_name, geo_level)
                VALUES ('NG025', 'Lagos', 'state')
                ON CONFLICT (geo_code) DO UPDATE SET
                    geo_name = EXCLUDED.geo_name,
                    geo_level = EXCLUDED.geo_level
                """
            )
        )

    after = _query(
        "SELECT parent_id FROM geographies WHERE geo_code = 'NG025'"
    )[0][0]

    assert after == before
