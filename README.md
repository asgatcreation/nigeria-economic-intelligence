# Nigeria Economic and Labour Market Intelligence

A reproducible data science project for exploring, analysing, and modelling
Nigeria's economic and labour-market indicators.

## Technology stack

- Python for data engineering, statistical analysis, and machine learning
- R for statistical modelling and survey analysis
- PostgreSQL for structured data storage
- SQL for data querying and analytical transformations
- Docker for isolated database infrastructure

## Project status

The ingestion pipeline is complete: validated CSV imports are recorded as
tracked batches, every value change is captured in a revision history, and
schema changes are applied through a migration ledger. No real economic data
has been loaded yet — the only data in the repository is a clearly labelled
synthetic file used to exercise the pipeline.

## Getting started

### 1. Start the database

The database runs in Docker and is published on `127.0.0.1:5434` so it does
not collide with other local PostgreSQL instances.

```bash
docker compose up -d
```

Credentials are read from `.env` (not committed). It must define:

```
POSTGRES_USER=...
POSTGRES_PASSWORD=...
POSTGRES_DB=...
```

### 2. Install the Python package

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e ".[analysis,dev]"
```

Installing in editable mode is what puts `nigeria_economic_intelligence` on
the import path; the test suite will not collect without it.

### 3. Apply the schema

```bash
python -m nigeria_economic_intelligence.migrate up
```

### 4. Run the tests

```bash
python -m pytest
```

Most tests talk to the running database, so step 1 and step 3 must be done
first.

## Working with migrations

Migrations are plain `.sql` files in `sql/`, applied in filename order and
recorded in the `schema_migrations` table along with a checksum of each file.

```bash
python -m nigeria_economic_intelligence.migrate status    # what has run
python -m nigeria_economic_intelligence.migrate up        # apply pending
python -m nigeria_economic_intelligence.migrate baseline  # record without running
```

Each migration runs in its own transaction and is rolled back if it fails.
Editing a migration that has already been applied is refused — the checksum
no longer matches — so schema changes go into a new numbered file instead.
`baseline` exists for adopting a database whose schema was created outside
the runner.

## Importing data

```bash
# Check a file without touching the database
python -m nigeria_economic_intelligence.ingestion path/to/file.csv --validate-only

# Validate and import
python -m nigeria_economic_intelligence.ingestion path/to/file.csv
```

### Required CSV columns

`source_code`, `source_name`, `geo_code`, `geo_name`, `geo_level`,
`indicator_code`, `indicator_name`, `domain`, `period_start`, `period_end`,
`value`.

### Optional columns

`organization`, `source_url`, `methodology`, `accessed_on`, `source_notes`,
`indicator_unit`, `indicator_description`, `frequency`, `unit`,
`observation_status`, `notes`.

See `data/reference/demo_synthetic_indicators.csv` for a working example.

### How an import behaves

Validation is all-or-nothing: a single bad row rejects the whole file, and
nothing is written to the warehouse. Observations are then upserted in one
transaction, so a partially applied import is not possible.

Every import — successful or rejected — is recorded in
`data_import_batches` with the filename, a SHA-256 digest of the file, row
counts, and the error message if it failed. Imported observations carry
`last_import_batch_id`, so any value in the warehouse can be traced back to
the file it came from.

Re-importing a file whose values have changed updates the observations in
place and the revision trigger records the before-and-after values in
`indicator_observation_revisions`, attributed to the import batch that made
the change. Manual updates outside an import are still recorded, with a null
`batch_id`.

## Database schema

| Table | Purpose |
| --- | --- |
| `data_sources` | Provenance: who published the data, how, and when it was accessed |
| `geographies` | Nigerian geographic units, self-referencing for hierarchy |
| `indicators` | Indicator definitions, domain, unit, and frequency |
| `indicator_observations` | The measured values, unique per indicator/geography/source/period |
| `indicator_observation_revisions` | Audit trail of every value, unit, status, or note change |
| `data_import_batches` | One row per ingestion attempt, with row counts and outcome |
| `schema_migrations` | Which migration files have been applied, with checksums |

## Repository layout

```
data/reference/   synthetic data committed to the repository
data/raw/         source files, not committed
data/processed/   derived datasets, not committed
docs/             written analysis and documentation
notebooks/        exploratory Jupyter notebooks
r/                R scripts for statistical modelling
reports/          generated output
sql/              numbered migrations
src/              the nigeria_economic_intelligence package
tests/            pytest suite and an R connectivity check
```

## R connectivity

```bash
Rscript tests/test_r_postgres.R
```

Requires the `DBI` and `RPostgres` packages.

## Data integrity

No real economic figures are invented or assumed anywhere in this project.
The only values in the repository are in
`data/reference/demo_synthetic_indicators.csv`, which is labelled synthetic
and exists solely to exercise the pipeline. Real indicator data must be
imported from a cited source with its provenance recorded in `data_sources`.
