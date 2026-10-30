"""Thin wrapper around the migration runner.

Prefer `python -m nigeria_economic_intelligence.migrate` (or `nei-migrate`),
which applies every pending migration in order and records it in the
schema_migrations ledger.
"""

from nigeria_economic_intelligence.migrate import main

if __name__ == "__main__":
    main()
