# Learning checkpoint — 2026-09-06

Stages 1 and 2 are complete. Live batch ingestion and PostgreSQL setup are
verified. Stage 5 normalization and transactional single-snapshot loading are implemented.

Implemented: shared configuration validation, single-city API requests, bounded
retries with Retry-After handling, immutable raw snapshot writing with a
completion marker, response-contract validation, and an ingestion CLI.

Verification: `make check` validates configuration, the stored Kyiv fixture, and
48 offline tests. Live requests and raw files under `data/raw` are not required
for those checks. The committed fixture is retained for reproducibility.

Batch collection is now implemented with `--all`: active cities run sequentially,
successful snapshots survive other city failures, and any failure returns exit
code 1. Offline tests cover success, network and contract failures, inactive
cities, and conflicting CLI options. The user verified a live batch with 10
successes and no failures.

PostgreSQL runs through Compose. The local host port is 5433 because an existing
PostgreSQL uses 5432. The database and user are weather; server timezone is UTC.
The three raw tables are created. `make check-db` verifies forecast keys and
relationships with rollback-only test rows. Normalization preserves 168 hourly
records, UTC timestamps, nulls, and snapshot identity.

Snapshot preparation is implemented and verified against a saved Kyiv response.
It requires _SUCCESS and uses saved request parameters and retrieval metadata.
Transactional loading is implemented in load.py. The saved Kyiv snapshot
20260905T121859.750902Z was loaded and replayed; 168 rows remain. Three real
integration tests verify replay, new versions, conflict rejection, and rollback.
Run make check-load with PostgreSQL running; make check still runs 48 offline tests.
Bulk replay is implemented and verified. The first run loaded 10 additional
snapshots, found 1 already loaded, and skipped 1 older unmarked Kyiv directory.
The second run loaded 0 and found all 11 already loaded. Warehouse totals are
10 cities, 11 snapshots, and 1848 hourly rows. Thirteen loader checks pass (three
real database tests and ten simulated batch/settings checks).
Stage 6 testing review is complete: raw preservation, configuration failures,
HTTP behavior, and database settings now have reusable tests. All three check
commands passed on 2026-09-06; see docs/testing.md.
Stage 7 is complete: three sources, three staging views, and eleven dbt tests.
Stage 8 is in progress. `int_forecast_versions` preserves the hourly grain and
adds exact interval and decimal-hour lead times. Its six tests protect required
fields and composite uniqueness. The full dbt build now passes four views and
seventeen tests: PASS=21. The model retains 1,848 rows, including 141 valid
negative lead times. The isolated dbt environment uses Python 3.12, Core
1.11.14, adapter 1.11.0. See docs/dbt.md.
Image digest pinning remains outstanding for exact Docker reproducibility.

Continue with short practical explanations and focused changes. Explain the
engineering decision, show relevant code, provide a command and expected output.
Proceed to the next step after results without asking for a separate “yes”.

Important boundaries:

- `retrieved_at` identifies when the response body finished downloading;
  `forecast_at` will identify each hour being forecast.
- Preserve separate retrieval snapshots for the same city and forecast hour.
- `_SUCCESS` means raw writing completed, not that validation passed.
- Validation failures retain raw data; future loaders must validate it again.
- A new live request creates a new snapshot; database replay now verifies existing records without adding duplicates.
- Earlier raw snapshots made before completion markers were introduced are
  unchanged and may lack `_SUCCESS`.
