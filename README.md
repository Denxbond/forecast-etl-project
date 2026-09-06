# Open-Meteo Forecast ETL

A local, versioned weather-forecast data pipeline built as a data engineering
portfolio project.

The pipeline will collect hourly forecasts for ten cities, preserve every raw
API response, load normalized forecast snapshots into PostgreSQL, transform the
data with dbt, and orchestrate the workflow with Airflow.

> Project status: Stage 7 — dbt sources and staging — is complete. Three
> staging views and eleven data tests pass, preserving every retrieval version.
> Next: Stage 8 — forecast-version transformations.
> See [the local dbt guide](docs/dbt.md) for setup and commands.
> See [the testing guide](docs/testing.md) for checks and known limits.

## Why this project exists

The main learning goal is to build a small but production-minded batch pipeline
and understand its engineering decisions. In particular, the project preserves
multiple predictions for the same future hour instead of overwriting older
forecasts.

## Planned architecture

```text
Open-Meteo Forecast API
        |
        v
Python ingestion
        |----> immutable raw JSON
        v
PostgreSQL raw tables
        v
dbt sources -> staging -> intermediate -> marts
        ^
        |
Airflow scheduling and orchestration
```

The full local environment will use Docker Compose. Airflow will be added only
after ingestion and dbt can run independently.

## Initial scope

- Ten configured cities
- Seven days of hourly forecasts
- Temperature at 2 m
- Precipitation
- Wind speed at 10 m
- WMO weather code
- One collection every six hours
- UTC storage with city timezones retained for local reporting
- Append-only forecast versions

## Repository layout

```text
config/                 Version-controlled pipeline and city configuration
dags/                   Airflow DAGs (added in a later stage)
data/raw/               Local raw API responses; contents are not committed
dbt/weather_dbt/        dbt project and analytical models
docs/                   Architecture and design documentation
scripts/                Small development and validation utilities
sql/init/               PostgreSQL initialization scripts
src/weather_pipeline/   Python application package
tests/                  Unit, integration, and stored API fixture tests
```

Folders that belong to later stages contain placeholders so the intended
boundaries are visible without pretending those components already exist.

## Configuration

Committed, non-secret behavior is stored in:

- `config/pipeline.toml` for the API contract and ingestion policy.
- `config/cities.csv` for the city list and stable city identifiers.

Machine-specific values and credentials will come from environment variables.
Copy `.env.example` to `.env` when a later stage needs those values. Never
commit `.env`.

All API timestamps will be requested and stored in UTC. The `timezone` column
in `cities.csv` will later be used to derive local forecast dates in dbt.

## Dependency strategy

- Host utilities support Python 3.11 through 3.14. Code is written to the
  Python 3.11 language level so the later Airflow container can use its own
  separately pinned, officially supported Python runtime.
- The ingestion package, test tools, dbt, and Airflow dependencies will be kept
  in separate groups so Airflow cannot unnecessarily constrain every tool.
- Direct dependencies will be introduced only when a stage needs them.
- Exact versions, including transitive dependencies, will be locked before the
  corresponding stage is considered complete.
- Airflow will use the official constraints matching its Python and Airflow
  versions inside Docker rather than being installed into the basic local
  Python environment.

Offline validation uses only the Python standard library. Warehouse loading uses
the `warehouse` optional dependency group (Psycopg and python-dotenv).
`requirements-warehouse.txt` locks the runtime packages verified on macOS with
Python 3.14; other platforms/runtimes still need their own dependency verification.

## Development commands

```bash
make help          # list the available commands
make bootstrap     # create .venv and a local .env file
make check-config  # validate pipeline.toml and cities.csv
make inspect-fixture # inspect and validate the saved API response
make check         # run all checks available at the current stage
make check-python  # run offline Python tests
```

To validate Stage 1 without creating a virtual environment:

```bash
make check
```

Expected result:

```text
Configuration valid: 10 active cities, 4 hourly variables, 7 forecast days.
Fixture valid: 168 hourly rows from 2026-09-05T00:00 to 2026-09-11T23:00.
```

See [`docs/api-contract.md`](docs/api-contract.md) for the response structure,
field meanings, and assumptions discovered from the live request.

## Forecast ingestion (Stage 3)

From the repository root, make a live request and preserve its response:

```bash
PYTHONPATH=src python3 -m weather_pipeline.ingest --city kyiv
```

Collect every active city sequentially:

```bash
PYTHONPATH=src python3 -m weather_pipeline.ingest --all
```

Use either `--city` or `--all`. Batch collection continues after individual
network, storage, or contract failures and preserves successful snapshots.
The summary reports city successes and failures; any city failure returns exit
code 1. Each city has its own retrieval timestamp. Retrying `--all` fetches every
active city again; use `--city CITY_ID` to retry only a failed city.

The command validates configuration and requires a known, active city. It uses
the configured timeout and retry policy, then saves the original response bytes,
request metadata, and UTC retrieval timestamp in a new snapshot directory.
`_SUCCESS` marks a completed save; it does not indicate API contract validation.
Existing snapshot directories cannot be overwritten. Each new live retrieval
creates a new snapshot, even when forecast values are unchanged.

Output defaults to `data/raw`. Override it with `--raw-dir` or the exported
`RAW_DATA_DIR` environment variable; relative paths resolve from the repository
root. The command does not automatically read `.env`.

After saving, the command validates response structure, UTC offset, grid
coordinates, units, hourly coverage and measurement types. Contract failures
retain the raw snapshot and report its path, returning exit code 1. Null
measurements remain allowed; `_SUCCESS` is not a validation certificate.
Offline tests run through `make check` without network calls. The live batch
was verified with 10 successful cities and no failures.

## Loading a saved snapshot

Install the warehouse dependencies in an existing `.venv`:

```bash
make install-warehouse
```

Load a completed snapshot (replace the example path with an existing directory):

```bash
PYTHONPATH=src .venv/bin/python -m weather_pipeline.load data/raw/CITY_ID/SNAPSHOT_TIMESTAMP
make check-load
```

Replay all saved snapshots under a raw root:

```bash
PYTHONPATH=src .venv/bin/python -m weather_pipeline.load --all data/raw
```

Discovery scans `ROOT/city/snapshot` directories in sorted order. Each completed
snapshot gets its own connection and transaction. The summary distinguishes
loaded, already-loaded, failed, and incomplete snapshots. Missing `_SUCCESS`
means skip as incomplete (including older snapshots made before markers existed).
Incomplete skips alone do not fail the run; validation or loading failures return
exit code 1 after the remaining snapshots are attempted. Missing or empty roots
also fail. Raw files are never modified, and replay makes no API requests.

The loader reads the project `.env`, with exported environment variables taking
precedence. It validates and normalizes the saved files before connecting. One
transaction inserts a missing configured city, its snapshot, and all hourly rows.
Existing city records are left unchanged; historical snapshots can be loaded for
inactive configured cities. City configuration synchronization is not implemented.

An identical replay adds nothing. An existing snapshot key with different request
parameters, grid coordinates, or hourly records raises an error rather than
overwriting data. Moving a raw file does not change its snapshot identity; the
original stored path remains unchanged. The database does not store the exact
response bytes, which remain in raw files. Idempotency compares stored fields,
not byte-level differences in JSON formatting or unused response metadata.

`make check-load` runs three real database integration tests with rolled-back
test records and ten simulated batch/settings checks. `make check` remains offline and
does not require the driver.

## Planned warehouse models

Stage 4 database setup is defined in `compose.yaml`. Docker Compose reads the
existing local `.env` automatically. Start PostgreSQL with:

```bash
docker compose config --quiet
docker compose up -d --wait warehouse
docker compose ps
```

The service uses PostgreSQL 17.11, stores data in a named Docker volume, and
listens only on localhost at `WAREHOUSE_PORT` (default 5432). Server time is UTC.
A health check waits until PostgreSQL accepts connections. Create the ingestion
tables explicitly with `make db-init`, then list them with `make db-tables`.
Run `make check-db` for rollback-only database constraint checks.
The SQL in `sql/init/001_ingestion_schema.sql` creates `raw.city`,
`raw.forecast_snapshot`, and `raw.hourly_forecast` in one transaction. It works
with an existing volume; no volume reset is required. Rerunning skips existing
tables but does not upgrade their definitions.
The image tag fixes the PostgreSQL patch and
Debian variant; digest pinning is still needed for exact image reproducibility.

Stop the container while retaining its data with `docker compose stop warehouse`.
`docker compose down` also retains the named volume; adding `--volumes` deletes
it. Database environment variables initialize an empty volume only: editing
`.env` later does not rename existing databases/users or change their passwords.

- `dim_city`
- `fct_hourly_forecast`
- `mart_daily_city_forecast`
- `mart_forecast_changes`

The hourly fact grain will be one city, one forecast hour, and one retrieval
snapshot. This preserves changing predictions over time.

## Roadmap

1. Repository foundation
2. API exploration
3. Python API client and raw JSON landing
4. PostgreSQL and Docker Compose
5. Normalized, idempotent loading
6. Python tests
7. dbt sources and staging
8. Forecast-version transformations
9. Dimensions, facts, and marts
10. Airflow orchestration
11. Integration tests and GitHub Actions
12. Portfolio documentation

## Data source and attribution

Weather data will be provided by [Open-Meteo](https://open-meteo.com/), under
its applicable terms and CC BY 4.0 attribution requirements. The free API is
used only for this non-commercial educational project.

## Documentation still to be added

- Detailed data model and column dictionary
- Failure, retry, and replay runbook
- Architecture diagram
- Example analytical queries
- CI status (test strategy is documented in `docs/testing.md`)
- Screenshots of Airflow and dbt documentation
- Known limitations and future improvements
