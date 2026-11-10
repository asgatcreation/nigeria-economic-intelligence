# Nigeria Economic and Labour Market Intelligence

A reproducible data science project for exploring, analysing, and modelling
Nigeria's economic and labour-market indicators.

## Technology stack

- Python for data engineering, statistical analysis, and machine learning
- R for statistical modelling and survey analysis
- PostgreSQL for structured data storage
- SQL for data querying and analytical transformations
- Docker for isolated database infrastructure

## Findings

**[Read the analysis: Nigeria — growth, prices, work and population,
1991–2025](reports/nigeria_economic_findings.md)**

708 observations across 20 indicators, national and for all 36 states
plus the FCT. The headline results:

- Income per person **peaked in 2015** and is still 8.4% below it a decade
  later.
- Measured unemployment of 3.1% sits alongside **66.5% vulnerable
  employment** — in Nigeria, job quality rather than joblessness is the
  binding constraint, and the unemployment rate is close to uninformative.
- Labour left agriculture for services while manufacturing's share of
  output fell from 19.5% to 8.3% of GDP: structural change without
  industrialisation.
- **Age dependency splits the country**: each 100 working-age people
  support 60 dependants in Lagos but 107 in Bauchi, so the national
  averages describe no actual state well.

Every number in the report is computed from the warehouse by
[`analysis.py`](src/nigeria_economic_intelligence/analysis.py) and
reproducible with one command. Nothing is hand-entered.

## Project status

The pipeline is complete and loaded with real data. Validated imports are
recorded as tracked batches, every value change is captured in a revision
history, and schema changes are applied through a migration ledger.

State-level data is loaded for all 36 states and the FCT, arranged under
the six geopolitical zones. The remaining gap is state *economic* data:
the NBS publishes state GDP, poverty and unemployment as PDF reports
rather than in machine-readable form, so only demographic structure is
available at that level.

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

### Loading real data

The World Bank connector fetches Nigeria indicators and writes them in the
format above, so the import goes through the same validation, transactions
and batch tracking as any other file:

```bash
# National indicators from the World Bank
python -m nigeria_economic_intelligence.sources.worldbank --ingest

# State population structure for all 37 states, from HDX
python -m nigeria_economic_intelligence.sources.hdx_population --ingest

# Or fetch only, to inspect the CSV first
python -m nigeria_economic_intelligence.sources.worldbank
```

Seven of the fourteen series are ILO *modelled* estimates rather than
Nigerian survey results. Those are stored with
`observation_status = 'estimated'` and a note recording that they are not
comparable with NBS published figures, so the distinction lives in the data
rather than only in documentation.

## Running the analysis

```bash
python -m nigeria_economic_intelligence.analysis            # print findings
python -m nigeria_economic_intelligence.analysis --figures  # and write charts
```

Findings are read from the warehouse by SQL and computed in code, so the
report regenerates after any re-import. Figures are written to
`reports/figures/`.

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

Geography is hierarchical: the 37 states hang off six geopolitical zones,
which hang off the country, so state observations roll up to zone and
national level by walking `parent_id`.

## Repository layout

```
data/reference/   synthetic data committed to the repository
data/raw/         source files, not committed
data/processed/   derived datasets, not committed
docs/             written analysis and documentation
notebooks/        exploratory Jupyter notebooks
r/                R scripts for statistical modelling
reports/          the written analysis and its figures
sql/              numbered migrations
src/              the nigeria_economic_intelligence package
src/.../sources/  connectors that fetch from external publishers
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
