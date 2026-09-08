# Local dbt workflow

Stage 7 uses free, local dbt Core. No dbt website account is required.
Python handles ingestion and loading; dbt executes SQL inside PostgreSQL.

## Environments and connection

- `.venv`: ingestion, loading, and the wrapper's python-dotenv dependency.
- `.venv-dbt`: Python 3.12, dbt Core 1.11.14, PostgreSQL adapter 1.11.0.
- `requirements-dbt.in`: direct dependency pins.
- `requirements-dbt.txt`: installed dependency versions verified on macOS/Python 3.12.

`make install-dbt` creates the isolated dbt environment from the lock.
The wrapper `scripts/run_dbt.py` uses `.venv-dbt/bin/dbt` explicitly, reads the
project `.env`, and lets exported environment variables override file values.
Anonymous dbt usage reporting is disabled by the wrapper.

The wrapper copies `profiles.example.yml` to ignored `profiles.yml` if missing.
The profile uses environment references; the password is passed under a dbt
secret environment variable. The target database is `weather`; generated views
are in `staging`. The development host port is 5433.

## Commands

Run from the repository root with PostgreSQL running and the raw schema loaded:

```bash
make dbt-debug    # validate configuration and database connectivity
make dbt-sources  # list source declarations; does not query source contents
make dbt-build    # build views and run data tests
```

To work on one model:

```bash
.venv/bin/python scripts/run_dbt.py build --select stg_city
```

`run` builds models, `test` runs data tests, and `build` builds models and runs
their tests. A data test returns violating rows: zero rows means it passes.
These tests query real warehouse data, unlike mocked HTTP tests in Python.

## Sources, models, and grain

`sources.yml` maps the logical source name `weather_raw` to PostgreSQL schema
`raw`. `source()` references those existing inputs; `ref()` references dbt models
and records model dependencies.

| Source | Staging view | One row represents |
| --- | --- | --- |
| `raw.city` | `staging.stg_city` | One city |
| `raw.forecast_snapshot` | `staging.stg_forecast_snapshot` | One city and retrieval |
| `raw.hourly_forecast` | `staging.stg_hourly_forecast` | One city, retrieval, and forecast hour |

City staging clarifies coordinate, timezone, and active-flag names. All staging
models preserve rows and source types. Views store queries rather than separate
data copies. No latest-version filtering or daily aggregation is applied.
Null measurements, inactive cities, and forecast hours before retrieval remain.

The eleven data tests check required keys, single/composite uniqueness, and
city/snapshot relationships. Composite-key checks use SQL files in `tests/`;
they do not require an additional dbt package.

## Stage 7 verification

On 2026-09-06, `dbt build` passed all three views and eleven tests:
`PASS=14 WARN=0 ERROR=0`. Source/staging counts matched at 10 cities,
11 snapshots, and 1848 hourly records. Counts describe this checkpoint, not
permanent assertions: new retrievals will increase them.

## Stage 8 forecast versions

`int_forecast_versions` keeps the hourly key `(city_id, retrieved_at,
forecast_at)` and adds two representations of lead time:

- `forecast_lead_time`: the exact PostgreSQL interval `forecast_at - retrieved_at`.
- `forecast_lead_hours`: the same difference expressed as decimal hours for
  filtering, charting, and future horizon buckets.
- `forecast_version_number`: chronological retrieval order for each city and
  forecast hour, starting at 1.
- `is_latest_forecast_version`: identifies the newest retained prediction
  without removing its history.

Lead time may be negative because the API's forecast window begins at midnight,
which can precede retrieval. The model does not filter those rows or collapse
retrieval versions. Nine model tests check required fields, composite
uniqueness, contiguous version numbering, and exactly one latest row per
city/forecast hour. On 2026-09-08, the full build passed four views and twenty
tests: `PASS=24 WARN=0 ERROR=0`.

Image digest pinning, cross-platform dependency verification, and later CI
remain separate work.
