# Learning checkpoint — 2026-09-05

Stages 1 and 2 are complete. Live batch ingestion and PostgreSQL setup are
verified. Stage 5 normalization is implemented; transactional loading is next.

Implemented: shared configuration validation, single-city API requests, bounded
retries with Retry-After handling, immutable raw snapshot writing with a
completion marker, response-contract validation, and an ingestion CLI.

Verification: `make check` validates configuration, the stored Kyiv fixture, and
24 offline tests. Live requests and raw files under `data/raw` are not required
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

Next: read a completed snapshot directory, validate its metadata and response,
then prepare snapshot and hourly records for transactional, idempotent loading.
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
- A new live request creates a new snapshot; database replay idempotency is not
  implemented yet.
- Earlier raw snapshots made before completion markers were introduced are
  unchanged and may lack `_SUCCESS`.
