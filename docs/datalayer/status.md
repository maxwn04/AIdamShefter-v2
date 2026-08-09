# Datalayer Implementation Status

Last updated: 2026-08-09

## Goal

Implement the planned platform datalayer as a dependency-ordered PR stack on
top of the backend API and PostgreSQL foundation.

## Stack

| Layer | Branch | Scope | Status |
| --- | --- | --- | --- |
| 1 | `codex/datalayer-foundation` | Architecture/docs, snapshot schema contract, workflow/source contracts, endpoint records, local file storage | Complete locally |
| 2 | TBD | PostgreSQL ingestion managers, refresh workflow, composition, API | Pending |
| 3 | TBD | Snapshot selection/lifecycle and deterministic SQLite projection | Pending |
| 4 | TBD | Frozen query runtime, reporter integration, compatibility, cleanup | Pending |

Branch names and exact boundaries may be tightened after the repository audit,
but each layer must remain independently reviewable and tested.

## Current Work

- Latest `origin/main` (`32b2d88`) is present.
- The six datalayer architecture documents are drafted and under review as the
  implementation contract.
- Repository/schema/API, legacy-reuse, and reporter-integration audits are
  complete.
- Foundation contracts, canonical scope keys, discriminated Sleeper attempts,
  exact Decimal-first canonical JSON, configuration, and the concrete
  content-addressed local file store are implemented.
- Snapshot model/migration `0007` now supplies active build-key uniqueness, one
  projection version, failure metadata, exact response-hash membership, and
  terminal expiration semantics.
- All initial endpoint families now have canonical requests, completeness
  rules, immutable normalized records, deterministic ordering, and fixture-backed
  tests. Their public vocabulary is consistently `build_*_request`,
  `validate_*_completeness`, and `normalize_*`.
- The best-principles review removed shallow normalizer forwarding functions,
  kept one deep manager per persistence aggregate, and corrected the initial
  HTTP contract to synchronous `/api/v1` behavior until a worker exists.
- The full repository suite passes (347 tests, with 51 PostgreSQL-dependent
  tests skipped); offline Alembic upgrade and downgrade SQL both compile through
  `0007`.
- The foundation layer is complete and committed locally. `gh stack init` is
  awaiting explicit user approval after the execution policy rejected the
  GitHub stack mutation.

## Coordination

The root agent owns edits to this file and `log.md` to avoid concurrent append
conflicts. Sub-agents read these files before their assigned slice and report
findings through agent messages; the root agent records decisions and progress
here.

## Required Gates

- Focused unit and integration tests for every stack layer.
- Existing datalayer query behavior characterized before migration.
- PostgreSQL manager tests use real database infrastructure where available.
- Snapshot tests build and open real SQLite artifacts.
- Full repository test suite passes before the final PR is declared complete.
- Every implementation requirement in the architecture docs is either proven
  by code/tests or explicitly deferred in those docs.

## Blockers

- Initializing/submitting the GitHub stack is paused because `gh stack init`
  was rejected as a potentially mutating GitHub operation. No alternative stack
  metadata was created.
- Production reporter cutover requires a generation service/manager that does
  not exist in the current tree. This is a later stack dependency, not a
  foundation blocker; it must be implemented or explicitly split as a
  prerequisite before final cutover can be claimed.
- A local PostgreSQL container is healthy, but the disposable database test
  suite creates and drops databases and local execution was denied by the
  environment's destructive-action policy. The isolated migration harness and
  assertions are present; live constraint execution remains a CI gate.
