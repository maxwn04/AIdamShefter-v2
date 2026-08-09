# Handoff: Datalayer Platform Implementation

## Primary Goals

- Replace the legacy fresh-load-only datalayer with a durable service architecture while preserving its valuable Sleeper normalization and query behavior.
- Keep PostgreSQL as the durable audit/current-state store and build immutable, cutoff-safe SQLite projections for reporter generations.
- Keep V1 operationally simple: synchronous refreshes, one attempt per scope, and content-addressed local filesystem storage rather than a remote object store.
- Land the work as reviewable dependency-ordered branches and use `docs/datalayer/status.md` plus `docs/datalayer/log.md` as the running implementation record.

## Current State

- Base: `main` / `origin/main` at `32b2d88`.
- Layer 1 branch: `codex/datalayer-foundation`, commit `58762dd feat(datalayer): establish service foundation`.
  - Six architecture/transition documents under `docs/datalayer/`.
  - Snapshot contract migration `0007_datalayer_snapshot_contract.py` and ORM/docs updates.
  - Exact Decimal-first canonical JSON, local content-addressed file store, source client/contracts, and all initial Sleeper endpoint families with deterministic normalization tests.
- Layer 2 branch: `codex/datalayer-ingestion`, commit `197673d feat(datalayer): implement durable refresh ingestion`.
  - Deep `SleeperDataManager` with scoped request/payload audit, current projection apply, CAS/stale semantics, current/audit reads, and snapshot candidate/payload reads.
  - `DatalayerRefreshService` with fixed base planning, explicit/dynamic weekly planning, dependency-aware per-scope apply, partial failure behavior, and sanitized cancellation/internal failures.
  - Synchronous refresh POST plus refresh-status/request-audit GET routes under `/api/v1`.
  - API composition, `ManagerContext`, authoritative endpoint/scope validation in `backend/sleeper.py`, and local file/source configuration.
- Current branch: `codex/datalayer-snapshots`, pointing at Layer 2 before this handoff commit. No Layer 3 implementation was started.
- The working tree was clean before this handoff file. Two Layer 3 sub-agents were assigned snapshot-manager and selection slices, then explicitly interrupted before editing when the user paused the work.

## What Has Been Tried

- Fast-forwarded local `main` to the API foundation at `32b2d88` and built two local dependency-ordered commits.
- Used independent repository, legacy-reuse, API/schema, reporter-integration, and best-principles reviews.
- The principles review found and drove fixes for:
  - non-canonical PostgreSQL `jsonb::text` replay breaking payload hashes;
  - historical transaction replay overwriting authoritative current traded-pick ownership;
  - endpoint-kind/scope-key combinations capable of poisoning an unrelated normalized head;
  - broad exception masking that converted programming bugs into payload rejections;
  - recoverable reference-data failures aborting the whole refresh;
  - forward/cyclic refresh dependencies, duplicate status/error abstractions, and imprecise NFL-state record naming.
- Verification run after Layer 2 integration:
  - `.venv/bin/python -m pytest -q` -> `387 passed, 52 skipped`.
  - Skips are PostgreSQL-only tests because `AIDAM_TEST_DATABASE_URL` was not provided.
  - `.venv/bin/python -m compileall -q backend datalayer reporter_memory reporter_v2` passed.
  - `git diff --check` passed.
- The expanded real-PostgreSQL manager test covers competition isolation, payload dedup/canonical replay, failed-response preservation, stale/identical heads, authoritative empty roster/weekly/bracket replacement, and transaction/pick ownership authority when a database URL is available.

## What Has Not Worked

- `gh stack init --base main codex/datalayer-foundation` was rejected by the execution policy as a potentially mutating GitHub operation. No alternative stack metadata was created. The branches are ordinary local Git branches with the correct parent commits.
- Local live-PostgreSQL verification was not run. The repository harness creates and drops disposable databases; that destructive operation was denied by the environment policy. Treat those 52 skipped tests, especially `backend/tests/resources/sleeper_data/test_manager_postgres.py`, as a CI/resume gate.
- Production reporter cutover cannot be completed yet because the repository still has no generation service/manager that can pin a ready snapshot for the duration of a model run.

## Remaining Work

1. Layer 3 on `codex/datalayer-snapshots`:
   - implement `backend/resources/data_snapshots/` objects and deep lifecycle manager;
   - implement pure request selection for `through_week` plus `observed_through`, including Week 8 observed in Week 8 versus Week 8 observed in Week 10;
   - implement deterministic SQLite schema/materialization and sealed metadata/integrity verification;
   - compose `DatalayerSnapshotService`, local artifact sealing/reuse, and snapshot audit API routes;
   - open real SQLite artifacts in tests and run the live PostgreSQL lifecycle tests when an approved test URL exists.
2. Layer 4 on a child branch:
   - implement `FrozenLeagueData`, curated legacy-compatible queries, resolvers, and guarded SQL;
   - characterize/reuse legacy query behavior without preserving accidental complexity;
   - integrate snapshot pinning into a generation workflow, then cut reporter tools over;
   - remove obsolete legacy paths only after compatibility tests pass.
3. Stack/verification:
   - run all PostgreSQL tests in CI or an explicitly approved disposable database;
   - rerun the full suite, compileall, and whitespace checks after each layer;
   - initialize/submit the formal GitHub/Graphite stack if desired; current commits are already dependency ordered.

## Key References

- `docs/datalayer/status.md`: current layer status, gates, and blockers.
- `docs/datalayer/log.md`: chronological decisions and verification evidence.
- `docs/datalayer/architecture.md`: component boundaries and dependency direction.
- `docs/datalayer/ingestion.md`: implemented refresh/normalization semantics.
- `docs/datalayer/snapshots-and-query-runtime.md`: authoritative Layer 3 selection, lifecycle, and SQLite design.
- `docs/datalayer/application-contracts.md`: public service/manager/API contracts.
- `backend/resources/sleeper_data/manager.py`: Layer 2 persistence aggregate and snapshot input reads.
- `backend/services/datalayer/refresh_service.py`: standard refresh orchestration.
- `backend/tests/resources/sleeper_data/test_manager_postgres.py`: live PostgreSQL gate.
- `.venv/bin/python -m pytest -q`: full verification command.
