"""Apply SQL migrations in order and record which ones have run."""

from pathlib import Path
import argparse
import hashlib

from sqlalchemy import text

from .database import engine

PROJECT_ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS_DIR = PROJECT_ROOT / "sql"

LEDGER_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename TEXT PRIMARY KEY,
    checksum CHAR(64) NOT NULL,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    applied_by TEXT NOT NULL DEFAULT CURRENT_USER
)
"""


def _checksum(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def _ensure_ledger() -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(LEDGER_SQL)


def _applied() -> dict[str, str]:
    """Return the checksum recorded for each applied migration."""
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT filename, checksum FROM schema_migrations")
        ).all()

    return {filename: checksum for filename, checksum in rows}


def _migration_files() -> list[Path]:
    if not MIGRATIONS_DIR.is_dir():
        raise SystemExit(f"Migrations directory not found: {MIGRATIONS_DIR}")

    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def _record(connection, path: Path, sql: str) -> None:
    connection.execute(
        text(
            """
            INSERT INTO schema_migrations (filename, checksum)
            VALUES (:filename, :checksum)
            ON CONFLICT (filename) DO UPDATE SET
                checksum = EXCLUDED.checksum,
                applied_at = CURRENT_TIMESTAMP,
                applied_by = CURRENT_USER
            """
        ),
        {"filename": path.name, "checksum": _checksum(sql)},
    )


def _drifted(applied: dict[str, str], path: Path, sql: str) -> bool:
    recorded = applied.get(path.name)
    return recorded is not None and recorded != _checksum(sql)


def status() -> int:
    """Print the state of every migration file."""
    _ensure_ledger()
    applied = _applied()
    drift = 0

    for path in _migration_files():
        sql = path.read_text(encoding="utf-8")

        if path.name not in applied:
            state = "pending"
        elif _drifted(applied, path, sql):
            state = "applied (file changed since)"
            drift += 1
        else:
            state = "applied"

        print(f"{path.name:<45} {state}")

    orphaned = set(applied) - {p.name for p in _migration_files()}
    for filename in sorted(orphaned):
        print(f"{filename:<45} recorded but file missing")

    return drift


def upgrade(*, baseline: bool = False) -> int:
    """Apply every pending migration and return how many ran."""
    _ensure_ledger()
    applied = _applied()
    pending = [
        path
        for path in _migration_files()
        if path.name not in applied
    ]

    for path in _migration_files():
        sql = path.read_text(encoding="utf-8")
        if _drifted(applied, path, sql):
            raise SystemExit(
                f"Error: {path.name} changed after it was applied. "
                "Add a new migration instead of editing an applied one."
            )

    if not pending:
        print("Database is up to date; no migrations to apply.")
        return 0

    for path in pending:
        sql = path.read_text(encoding="utf-8")

        if not sql.strip():
            raise SystemExit(f"Error: migration file is empty: {path.name}")

        try:
            with engine.begin() as connection:
                if not baseline:
                    connection.exec_driver_sql(sql)
                _record(connection, path, sql)

        except SystemExit:
            raise

        except Exception as exc:
            print(
                f"Migration failed: {path.name}. "
                "The transaction was rolled back."
            )
            print(f"Error: {exc}")
            raise SystemExit(1) from exc

        verb = "Recorded" if baseline else "Applied"
        print(f"{verb}: {path.name}")

    print(f"{len(pending)} migration(s) {'recorded' if baseline else 'applied'}.")
    return len(pending)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply SQL migrations from the sql/ directory."
    )
    parser.add_argument(
        "command",
        nargs="?",
        default="up",
        choices=("up", "status", "baseline"),
        help=(
            "up: apply pending migrations (default); "
            "status: show migration state; "
            "baseline: mark pending migrations as applied without "
            "running them"
        ),
    )
    args = parser.parse_args()

    if args.command == "status":
        if status():
            raise SystemExit(1)
    elif args.command == "baseline":
        upgrade(baseline=True)
    else:
        upgrade()


if __name__ == "__main__":
    main()
