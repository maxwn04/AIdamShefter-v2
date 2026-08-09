# Datalayer Implementation Log

This is the chronological decision and verification log for the datalayer PR
stack. `status.md` is the current summary; this file preserves why the state
changed.

## 2026-08-09

- Fast-forwarded local `main` from `69de250` to `32b2d88`, bringing in the
  backend API application, composition root, route placeholders, and tests.
- Created `codex/datalayer-foundation` as the base branch for the planned stack.
- Began repository audit before assigning non-overlapping implementation slices.
- Settled coordination rule: the root agent updates `status.md` and `log.md`;
  sub-agents read them and return evidence/findings without concurrently editing
  these two files.
- Added immutable workflow contracts, canonical `ScopeKey`, a one-attempt
  Sleeper source client with discriminated/sanitized outcomes, and a concrete
  local file store that owns atomic writes, content addressing, containment,
  idempotent collision handling, and hash/size verification.
- Refreshed the local environment from `uv.lock` using
  `mise exec uv@0.11.25 -- uv sync --extra dev` after the API tests revealed the
  pre-existing virtual environment did not contain the newly pulled FastAPI
  dependencies.
- Verification: `.venv/bin/python -m pytest -q backend/tests/api
  backend/tests/services/datalayer` passes 19 tests.
- Reporter integration audit found no generation application layer yet. The
  frozen runtime can be built independently, but production reporter cutover
  must ultimately compose through a generation workflow that pins the ready
  snapshot before model execution.
- Completed three read-only audits. They confirmed reuse of the existing 19
  Sleeper ORM tables, session/API infrastructure, endpoint paths, fixture
  corpus, normalization calculations, and curated query behavior. They also
  identified required fixes rather than copy-forward behavior: Decimal-first
  source parsing, FK-aware apply ordering, cross-scope global-user ordering,
  exact snapshot membership hashes, deterministic SQLite derivation, and
  stronger query/SQL leakage guards.
- Added migration `0007_datalayer_snapshot_contract`: removed mode-based
  snapshot identity, consolidated projection compatibility, added failure
  metadata and response-hash membership, enforced one active row per build key,
  and made expiration terminal while preserving failed/expired audit history.
- Updated both datalayer and authoritative database schema docs, including new
  decision DB-032.
- Added Decimal-first JSON parsing and deterministic canonical encoding. Source
  fractional values no longer pass through binary float before normalization.
- Verification now includes 24 passing API/foundation/metadata tests, Python
  compilation, and successful offline Alembic `upgrade head --sql` plus
  `downgrade 0007:base --sql`.
- Completed all initial endpoint families for league metadata/users, NFL state,
  players, rosters, traded picks, weekly matchups/transactions, and playoff
  brackets. Requests and scope keys are canonical; endpoint records are
  immutable and sink-agnostic; malformed nested facts are rejected rather than
  silently dropped; fractional values remain `Decimal`.
- The final best-principles pass standardized endpoint names and removed
  one-line normalizer forwarding functions. It retained only boundaries that
  own meaningful invariants: the two workflow services, two persistence
  aggregates, snapshot materializer/runtime, and concrete local file store.
- Corrected the planned HTTP surface to the app's existing `/api/v1` prefix and
  synchronous `200 OK` refresh execution. Asynchronous `202` behavior is
  deferred until a worker boundary actually exists.
- Verification: API, new datalayer, and legacy datalayer tests pass together
  (148 tests in 0.56s); compilation and whitespace checks pass. A healthy local
  PostgreSQL container was available, but running the suite that creates and
  drops disposable databases was denied by the execution policy, so live
  constraint tests remain a CI gate.
- Full repository verification passes: 347 tests passed and 51 PostgreSQL-only
  tests skipped because `AIDAM_TEST_DATABASE_URL` was intentionally not supplied
  after the local create/drop harness was denied.
- Committed the complete foundation layer on `codex/datalayer-foundation`. The
  subsequent `gh stack init` request was
  rejected by the execution policy as a potentially mutating GitHub operation;
  no alternate stack initialization was attempted.
- Created local child branch `codex/datalayer-ingestion` from the committed
  foundation so implementation could continue without touching GitHub stack
  metadata. Split Layer 2 into non-overlapping persistence-manager,
  refresh-orchestration, and API/composition slices; root retains integration,
  schema follow-ups, and coordination-doc ownership.
- Implemented the Layer 2 persistence aggregate, refresh workflow, synchronous
  manual API, refresh/request audit APIs, and runtime composition. Explicit week
  requests persist their complete plan up front; omitted weeks resolve fresh NFL
  state and expand weekly scopes once.
- Moved canonical Sleeper endpoint/scope identity to `backend/sleeper.py` and
  enforce kind/scope/season/week/bracket agreement at both plan and attempt
  boundaries. Dependencies must precede their consumers in the persisted plan.
- The requested independent principles review found two runtime correctness
  bugs: raw PostgreSQL `jsonb::text` could not satisfy compact canonical hashes,
  and replayed historical transactions could overwrite authoritative current
  traded-pick ownership. Inline JSONB is now re-canonicalized before receipt
  verification, and only traded-picks updates current ownership; transactions
  create a missing natural identity only for move linkage.
- Added a typed reference-unavailable error so plausible catalog/core identity
  reconciliation failures reject only their endpoint scope. Removed a broad
  normalization catch that could hide programming bugs as source-data failures,
  duplicate service/resource status enums, empty error aliases, generic
  observation-only naming, and untyped payload helper casts.
- Verification after Layer 2 integration: 387 repository tests pass; 52
  PostgreSQL-dependent tests skip without `AIDAM_TEST_DATABASE_URL`; compileall
  and `git diff --check` pass. The live manager test was expanded to cover scope
  isolation, payload dedup/canonical replay, incomplete preservation,
  stale/identical behavior, authoritative empty replacement across roster,
  weekly, and bracket scopes, and transaction/pick ownership authority.
