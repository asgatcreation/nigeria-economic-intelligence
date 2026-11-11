"""Reconcile the validator's allowed values with the database.

ingestion.py holds the allowed domains, geography levels, frequencies
and observation statuses as Python sets so that validation works without
a database connection. The database holds the same lists as CHECK
constraints. Nothing keeps the two in step automatically, so a migration
that widens a constraint without updating the constant — or the reverse —
would let the validator and the schema disagree.

The failure that causes is nasty: a value the validator accepts but the
database rejects surfaces as an IntegrityError mid-import rather than as
a clean validation message, and a value the database accepts but the
validator rejects makes perfectly good data unloadable for no visible
reason. These tests pin them together.
"""

import re

import pytest
from sqlalchemy import text

from nigeria_economic_intelligence import ingestion
from nigeria_economic_intelligence.database import engine


def _check_clause(table: str, constraint: str) -> str:
    with engine.connect() as connection:
        clause = connection.execute(
            text(
                """
                SELECT pg_get_constraintdef(c.oid)
                FROM pg_constraint AS c
                WHERE c.conrelid = CAST(:table AS regclass)
                  AND c.conname = :constraint
                """
            ),
            {"table": table, "constraint": constraint},
        ).scalar_one_or_none()

    if clause is None:
        pytest.fail(f"constraint {constraint} not found on {table}")

    return clause


def _allowed_values(table: str, constraint: str) -> set[str]:
    """Pull the literal values out of a CHECK ... IN (...) clause."""
    return set(re.findall(r"'([^']+)'", _check_clause(table, constraint)))


def test_domains_match_the_database():
    assert ingestion.ALLOWED_DOMAINS == _allowed_values(
        "indicators", "indicators_domain_check"
    )


def test_frequencies_match_the_database():
    assert ingestion.ALLOWED_FREQUENCIES == _allowed_values(
        "indicators", "indicators_frequency_check"
    )


def test_geography_levels_match_the_database():
    constraint = next(
        name
        for name in _constraint_names("geographies")
        if "geo_level" in _check_clause("geographies", name)
    )

    assert ingestion.ALLOWED_GEO_LEVELS == _allowed_values(
        "geographies", constraint
    )


def test_observation_statuses_match_the_database():
    constraint = next(
        name
        for name in _constraint_names("indicator_observations")
        if "observation_status" in _check_clause(
            "indicator_observations", name
        )
    )

    assert ingestion.ALLOWED_STATUSES == _allowed_values(
        "indicator_observations", constraint
    )


def _constraint_names(table: str) -> list[str]:
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                SELECT conname
                FROM pg_constraint
                WHERE conrelid = CAST(:table AS regclass)
                  AND contype = 'c'
                """
            ),
            {"table": table},
        ).scalars().all()

    return list(rows)


def test_poverty_is_an_allowed_domain():
    """Migration 005 added it; both sides must agree."""
    assert "poverty" in ingestion.ALLOWED_DOMAINS
    assert "poverty" in _allowed_values(
        "indicators", "indicators_domain_check"
    )
