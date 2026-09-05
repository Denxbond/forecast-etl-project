# Open-Meteo Forecast ETL

A local, versioned weather-forecast data pipeline built as a data engineering
portfolio project.

The pipeline will collect hourly forecasts for ten cities, preserve every raw
API response, load normalized forecast snapshots into PostgreSQL, transform the
data with dbt, and orchestrate the workflow with Airflow.

> Project status: Stage 3 in progress — single-city ingestion and raw snapshot
> preservation are implemented. Database loading is not yet implemented.

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

This stage deliberately has no third-party Python dependencies. Its validation
command uses only the Python 3.11 standard library.

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

## Single-city ingestion (Stage 3)

From the repository root, make a live request and preserve its response:

```bash
PYTHONPATH=src python3 -m weather_pipeline.ingest --city kyiv
```

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
Offline tests run through `make check` without network calls. Multi-city
collection remains to be added before Stage 3 is complete.

## Planned warehouse models

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
- Test strategy and CI status
- Screenshots of Airflow and dbt documentation
- Known limitations and future improvements
