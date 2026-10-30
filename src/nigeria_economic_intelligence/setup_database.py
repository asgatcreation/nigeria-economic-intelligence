"""Deprecated: use the migration runner instead.

This module applied only `sql/001_initial_schema.sql`, which leaves a
database missing every later migration. `migrate` applies all of them in
order and records what it has run.
"""

from .migrate import upgrade


def main() -> None:
    print(
        "setup_database is deprecated; running the migration runner "
        "instead (python -m nigeria_economic_intelligence.migrate up)."
    )
    upgrade()


if __name__ == "__main__":
    main()
