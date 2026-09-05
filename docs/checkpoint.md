# Learning checkpoint — 2026-09-05

Stages 1 and 2 are complete. Stage 3 is in progress.

Implemented: shared configuration validation, single-city API requests, bounded
retries with Retry-After handling, immutable raw snapshot writing with a
completion marker, response-contract validation, and an ingestion CLI.

Verification: `make check` validates configuration, the stored Kyiv fixture, and
16 offline tests. Live requests and raw files under `data/raw` are not required
for those checks. The committed fixture is retained for reproducibility.

Next learning step: collect all active cities sequentially, keep successful
snapshots if another city fails, and return a failing batch exit code when any
city fails. Stage 4 (PostgreSQL and Docker Compose) has not started.

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
