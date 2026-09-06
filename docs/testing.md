# Testing guide

Stage 6 verification on 2026-09-06: all commands below passed.

## Commands and prerequisites

Run from the repository root:

| Command | Scope | Prerequisites | Expected result |
| --- | --- | --- | --- |
| `make check` | Configuration, stored fixture, offline Python tests | Python 3.11–3.14 standard library | 48 tests, `OK` |
| `make check-db` | PostgreSQL keys and relationships | Docker warehouse running; schema created | Four PASS notices and `ROLLBACK` |
| `make check-load` | Transactions, batch handling, connection settings | `.venv`, warehouse dependencies, running database and schema | 13 tests, `OK` |

Full local verification:

```bash
make check check-db check-load
```

The Makefile stops if a target fails. No check command requests live forecasts.
`make check` may print a failed-ingestion summary from a deliberately simulated
failure; unittest's final `OK` and the command exit status determine test success.

Database setup, if not already completed:

```bash
make bootstrap
make install-warehouse
docker compose up -d --wait warehouse
make db-init
```

Compose and the Python loader read the project `.env`. Set `WAREHOUSE_PORT` to
an available host port (5433 on the development Mac). `make check-load` uses
`.venv/bin/python`; `make check` uses `PYTHON`, defaulting to `python3`.

## What the tests protect

- Configuration: invalid numeric policies, unsupported units, duplicate cities,
  malformed CSV structure, invalid coordinates/timezones/flags.
- HTTP: request parameters, timeout forwarding, raw bytes, retrieval timing,
  bounded retries, Retry-After, certificate rejection, and response cleanup.
- Raw storage: exact bytes and metadata, overwrite rejection, and no completion
  marker after interrupted writes.
- Validation and normalization: array alignment, units, UTC, hourly coverage,
  numeric/null values, stable replay, and distinct retrieval identities.
- Snapshot preparation: completion markers, metadata, historical request
  parameters, response validation, and unchanged source files.
- Loading: two forecast versions coexist, replay adds no duplicates, conflicting
  content fails, and insertion errors roll back related records.
- Batch replay: per-snapshot failures do not stop later attempts; incomplete
  snapshots are skipped and counts/exit status reflect the results.
- Connection settings: temporary `.env` values, environment precedence, missing
  settings, literal passwords, and environment-only operation.

## Fixtures, isolation, and discovery

The committed Kyiv fixture is fixed evidence, not today's forecast. Tests modify
copies in memory or temporary directories. They do not edit real raw snapshots.
HTTP calls and sleeping are mocked at controlled boundaries.

`make check` discovers `test*.py` in `tests/unit`. `make check-load` discovers
`test_load*.py` in `tests/integration`: three tests use PostgreSQL; four batch
tests and six settings tests are simulated/offline but import warehouse packages.

Database tests use unique test city identifiers and rollback transactions.
The SQL constraint test also ends with rollback. Existing application data is
not removed. Do not remove the rollback guards when experimenting with tests.

## Limits and later work

These checks cover the current ingestion and loading guarantees, not every
possible failure. Concurrent loaders, process termination/power loss, filesystem
durability, and a multi-platform Python matrix are not tested. Live batch and
committed replay were verified separately from automated rollback tests.
Docker image digest pinning and cross-platform dependency locks remain
reproducibility work. dbt tests arrive with its models; GitHub Actions and broader
end-to-end automation remain Stage 11.
