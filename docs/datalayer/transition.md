# Legacy Datalayer Transition Plan

## Policy

This is behavioral reuse inside a clean architecture, not storage or API
compatibility work. Existing in-memory SQLite data, exports, cache files, CLI
commands, and persisted identifiers can be discarded and regenerated. No dual
reads, dual writes, import migrations, or wrapper maintained solely for the old
application should be introduced.

The implementation should preserve proven factual behavior through extracted
code and golden tests while replacing lifecycle and persistence assumptions.

## Behavior-First Reuse Rule

The default is to preserve proven behavior, not necessarily the old file, type,
or function boundary. For each legacy area, choose the implementation with the
fewest concepts in the final architecture:

1. move the code unchanged when its inputs, outputs, and ownership still fit;
2. extract a pure calculation when the surrounding SQLite DTO/lifecycle does
   not fit;
3. rewrite behind golden tests when keeping the old shape would require wrappers
   or adapters on both sides.

In particular:

- reuse endpoint paths, fixtures, fantasy calculations, derivations, and curated
  SQL aggressively;
- do not mandate legacy row dataclasses as the new canonical representation;
- do not add a provenance wrapper plus PostgreSQL adapter plus SQLite adapter
  merely to avoid changing one old DTO;
- establish golden output parity before and after every moved or rewritten
  module;
- require a concrete simplification or new correctness need for a rewrite, but
  count removal of adapter layers as a valid simplification.

This is still a clean replacement of storage/lifecycle APIs. Behavioral reuse
must make the final system smaller or safer, not preserve historical structure
for its own sake.

## Reuse Map

| Legacy area | Reuse | Target/change |
| --- | --- | --- |
| `datalayer/sleeper_data/sleeper_api/endpoints.py` | High | Keep endpoint paths and payload expectations inside explicit endpoint-family modules and validated scope-key builders |
| `sleeper_api/client.py` | Low | Keep error lessons and timeout defaults; replace filesystem cache and payload-only return with an auditable response envelope and injectable transport |
| `normalize/*.py` parsing and football calculations | High | Preserve pure logic and outputs through golden tests; extract it from SQLite-coupled functions when that produces a simpler shared record |
| `normalize/*.py` row dataclasses | Case by case | Keep a row type only when it naturally feeds the new consumer; replace it when preserving it would require two sink adapters or retain float/SQLite-specific semantics |
| Game, standings, profile, pick derivations | High | Move to snapshot derivations; add cutoff/reconstruction tests |
| `schema/` SQLite tables | High for snapshots | Version as the frozen reporter schema, add `snapshot_metadata` and optional internal identity columns; do not use as PostgreSQL models |
| `store/sqlite_store.py` | Medium | Reuse deterministic table creation/bulk insert ideas inside the materializer; add verification and read-only artifact lifecycle |
| `load.py` | Low as code, high as behavioral checklist | Split into refresh planning/execution, normalization commit, request selection, and snapshot materialization |
| `queries/*.py` | Very high | Move into the frozen query runtime, preserve contracts, add explicit snapshot identity/single-season scoping |
| `queries/_resolvers.py` | High | Preserve name/ID ambiguity behavior; optionally surface stable franchise/season-roster IDs |
| `queries/sql_tool.py` | Medium | Preserve result shape and auto-limit intent; strengthen statement parsing, readonly mode, deadlines, and JSON conversion |
| `SleeperLeagueData.from_file()` | High conceptually | Becomes `FrozenLeagueData.open()` with verified metadata and context-managed lifecycle |
| `SleeperLeagueData.load()` / `save_to_file()` | None as public API | Replaced by refresh and snapshot services |
| `datalayer/tools.py` | High contract reuse | Tool schemas/handlers move under reporter and call `FrozenLeagueData` |
| `sleeperdl` CLI | Selective | Rebuild only useful operator diagnostics on service APIs; do not preserve ephemeral load semantics |
| JSON fixture corpus | Very high | Becomes normalization, ingestion, snapshot, cutoff, and query-contract fixtures |

## Important Refactors

### 1. Split the legacy facade

The old facade owns four concerns: source configuration, load orchestration,
SQLite lifecycle, and curated queries. The new design has no direct replacement
class with all four responsibilities.

```text
SleeperLeagueData.load()       -> DatalayerRefreshService + DatalayerSnapshotService
SleeperLeagueData.from_file()  -> FrozenLeagueData.open()
SleeperLeagueData query calls  -> FrozenLeagueData / curated query modules
SleeperLeagueData.save_to_file -> LocalDatalayerFileStore owned by snapshot service
```

This split should land early so later code cannot continue depending on the
ephemeral-load lifecycle.

### 2. Normalize once without mandating the old DTO

Today many normalizers return dataclasses coupled to SQLite table vocabulary.
The target keeps a normalizer unchanged only when its result is already a
natural endpoint record for both current persistence and snapshot projection.
Otherwise, preserve its parsing/calculation logic and return a simpler new
endpoint record.

```text
raw Sleeper payload
  -> endpoint-family validation/normalization
  -> EndpointRecords
      -> NormalizedScopeManager current-view projection
      -> SQLite cutoff projection
```

Request provenance remains on `ApiRequest` and the selected-request manifest;
it is passed beside endpoint records instead of copied into a bundle hierarchy.
Snapshot-only derivations remain in the snapshot projection.

### 3. Separate observations from facts

The legacy cache can make a request disappear from runtime behavior. The new
client always performs the planned call, and `ApiRequestManager` records
the attempt. Payload hashes deduplicate bytes without deduplicating observations.

### 4. Make historical reconstruction physical

The legacy `week_override` becomes a required `through_week` plus an
`as_of_date` daily reuse label, selected raw requests, and cutoff-safe
projection. The date does not filter source observations. The first healthy
daily snapshot is reused, while recovery after failure or expiration may
reselect within the same daily key.

## Implementation Slices

Each slice should be independently testable and leave the reporter behavior
working through fixtures before production wiring advances.

### Slice 1: Contracts and fixture characterization

- Add datalayer workflow value objects, endpoint kinds, scope-key builders, and
  typed errors.
- Convert current query outputs into golden contract tests using existing
  Sleeper fixtures.
- Add characterization tests for every legacy normalizer and derivation before
  moving code.
- Define ingestion-normalizer and snapshot-projection version constants.
- Align snapshot persistence with the factual service contract: active build
  key, one projection version, failure metadata, request-response hashes, and
  terminal expiration.

**Exit:** fixture payloads have explicit expected endpoint records and query
results; migration `0007` upgrades/downgrades and its concurrency/immutability
constraints are proven before manager code depends on them.

### Slice 2: Deep persistence aggregates

- Implement resource-specific Sleeper managers against the completed PostgreSQL
  models.
- Implement content-addressed payload receipts and request recording.
- Implement scope-head compare-and-swap and atomic apply behavior.
- Make refresh finalization derive counts/status from child requests.

**Exit:** manager tests prove competition scope, empty replacement, stale
request rejection, identical-head advancement, payload deduplication, and short
transactions.

### Slice 3: Source adapter and refresh service

- Replace the legacy client with the typed response envelope and injectable
  transport.
- Implement the standard refresh plan in the service and provider behavior in
  endpoint-family modules.
- Reuse or extract legacy normalization calculations per endpoint based on the
  simplest resulting representation.
- Wire the one refresh workflow.

**Exit:** fixture-backed source responses populate the latest PostgreSQL view;
partial refreshes remain auditable and do not erase good heads.

### Slice 4: Snapshot selection and atomic identity

- Implement `DataSnapshotManager` against the snapshot contract completed in
  Slice 1.
- Implement the daily build key and claim/reuse it before candidate selection.
- Implement explicit season-stable requirement planning, request candidate
  reads, and pure selection of the latest complete observations compatible with
  `through_week`.
- Reuse the concrete `LocalDatalayerFileStore` from the source-I/O layer and
  verify selected payloads; each membership row retains its individual response
  SHA-256 rather than one aggregate identity hash.
- Implement `begin_or_get(build_key)` and snapshot lifecycle methods.
- Add bounded waiting plus atomic stale-build failure and unusable-artifact
  expiration; failed/expired history must not block a replacement claim.
- Make missing required scopes fail without a configurable incomplete mode.

**Exit:** the service can deterministically select an immutable in-memory source
manifest, and manager tests can atomically seal that membership with a synthetic
verified artifact receipt. Production membership is not persisted before the
artifact is ready.

### Slice 5: SQLite materializer

- Move/version the legacy schema as a snapshot-only schema.
- Add deterministic `snapshot_metadata` without snapshot UUID or creation time.
- Project endpoint records into rows.
- Extract games, standings, profiles, pick ownership, and season-context
  derivations.
- Centralize late current-state field policy in the projection and add integrity,
  provenance, cutoff, and artifact hash verification.
- Wire the real materializer and file store into the snapshot service and prove
  selection, payload replay, materialization, storage, and atomic sealing in one
  end-to-end integration test.

**Exit:** selected fixture request sets produce deterministic, verified SQLite
artifacts with no post-`through_week` week-scoped or volatile state, and the real
snapshot workflow returns a ready, hash-verified artifact with exact sealed
membership.

### Slice 6: Frozen query runtime and reporter integration

- Move curated queries and resolvers behind concrete `FrozenLeagueData`.
- Implement `FrozenLeagueData` context-managed read-only runtime.
- Harden guarded SQL.
- Move tool definitions/handlers into reporter and call the runtime directly.
- Rename snapshot-relative “current roster” behavior to “roster at cutoff.”
- Update generation service to call `get_or_create()`, pin the snapshot ID in
  the manifest, and run the reporter.

**Exit:** reporter contract tests pass against the new frozen artifact without
any source or PostgreSQL access during the agent loop.

### Slice 7: Current-data and audit API

- Add synchronous manual refresh/status HTTP routes.
- Add product read projections for overview, roster, matchup, transaction,
  refresh, request, and snapshot audit views.
- Add pagination and safe error translation.
- Leave worker polling as a future seam until an asynchronous worker exists.

**Exit:** the frontend can inspect current data and provenance without using the
reporter SQLite or raw SQL.

### Slice 8: Remove legacy runtime paths

- Remove the old ephemeral load entry point, filesystem cache, obsolete export
  path, and direct reporter dependency on `datalayer.tools`.
- Keep only fixtures or temporarily imported query/normalization modules still
  needed by the new package.
- Update packaging and docs to point to `backend/services/datalayer`.

**Exit:** production code has one refresh path, one snapshot path, and one
reporter query runtime. No dual behavior remains.

## Testing Strategy

### Pure unit tests

- endpoint request planning and stable scope keys;
- completeness validators, especially authoritative empty lists;
- every reused/extracted endpoint normalizer with existing JSON fixtures;
- `Decimal` preservation and JSON boundary conversion;
- request selection across `through_week` and available request-history
  combinations;
- daily build-key canonicalization and deterministic membership ordering;
- standings, games, profiles, picks, and reconstruction warnings;
- guarded SQL parser/limits/deadlines.

### PostgreSQL manager tests

Use real disposable PostgreSQL sessions and manager contexts to prove:

- competition isolation and explicit global catalog scope;
- payload hash deduplication with distinct request observations;
- old request finishing late cannot replace a newer head;
- identical newer payload advances observation head without rewriting rows;
- failed/incomplete response preserves current rows;
- complete empty response removes the old scope;
- normalized rows and head advance commit or roll back together;
- refresh final status/counts are derived transactionally;
- concurrent identical snapshot requests share one canonical build key;
- a crashed build becomes failed after the stale threshold and can be rebuilt;
- a late original builder cannot seal after its row is failed and a replacement
  claims the same daily key;
- failed, expired, missing-artifact, and corrupt-artifact rows do not poison a
  daily build key;
- snapshot membership and ready metadata seal atomically;
- ready snapshot fields are immutable.

### Snapshot integration tests

Build real SQLite files from fixture request histories and assert:

- a Week 8 snapshot with any caller-chosen date label contains no Week 9 facts;
- `as_of_date` and request timestamps do not filter candidate selection;
- a fresh Week 8 build may select a later complete correction scoped to Week 8;
- current season-stable settings, rather than historical league-payload
  settings, determine conditional request requirements;
- a later roster, user, player, or bracket response may supply reference data,
  while projection policy prevents later-week state from becoming cutoff truth;
- the first ready snapshot is reused for the same season/week/date/version,
  while a caller-chosen different date label may select later observations;
- recovery after failure/expiration may reselect newer eligible membership
  under the same coarse daily key and preserves both attempts for audit;
- changing only generation intent does not duplicate a factual snapshot;
- weekly lineup membership comes from the selected matchup payload;
- exact request IDs and hashes appear in snapshot provenance;
- missing required scopes fail ordinary builds;
- post-domain roster fields are copied, derived, or omitted only by the snapshot
  projection's explicit policy;
- the artifact hash changes when selected input or snapshot projection version
  changes;
- identical selected membership and projection version produce byte-equivalent
  artifacts, while one active daily build key prevents duplicate work;
- SQLite integrity and metadata validation fail closed.

### Query contract tests

Run the existing curated query suite against artifacts produced by the new
materializer. Compare canonicalized outputs to the legacy fixture baseline,
allowing only approved additions such as stable IDs or exact decimal formatting.

### Service tests

Inject fake transports/managers and use a temporary local file root, fake
clocks, and identity maps. Test workflow ordering and failure behavior without
patching private helpers. In
particular, assert that no manager transaction spans an HTTP request, artifact
file write, or SQLite build.

### API tests

Use dependency overrides and verify request validation, scope enforcement,
synchronous status reads, pagination, safe error translation, and absence of
private payload/storage details.

## Acceptance Criteria

The component is ready for platform use when:

- refreshes durably record every attempt and safely maintain current heads;
- current product reads are competition-scoped and do not return ORM rows;
- every snapshot seals exact selected request history and enforces its
  `through_week` domain boundary;
- every ready snapshot is immutable, hash-verified, and physically excludes
  post-`through_week` week-scoped and volatile state;
- reporter tools and guarded SQL operate only through `FrozenLeagueData`;
- core curated query behavior passes migrated legacy tests;
- no service, route, worker, or reporter tool imports ORM models or opens a
  database session;
- no transaction remains open during Sleeper, local-file, SQLite, or model work;
- there is no legacy cache, ephemeral production load path, or PostgreSQL SQL
  escape hatch;
- generation manifests pin the data snapshot ID and all relevant build/cutoff
  versions.
- retained version-2 artifacts open through the explicit compatibility reader,
  while new policy-version-2 generations seal projection-version-3 artifacts,
  manifest version 2, factual revision, and complete season coverage;
- operator readiness inspection is network-free and explicit preparation uses
  the same resolver, refresh coordinator, and builder as generation.

## Deliberately Deferred

- provider registries and generic provider-normalized facts;
- persistent games/standings projection builds in PostgreSQL;
- exact taxi/IR and intra-week roster ownership history;
- a generalized scheduler, leases, resumable snapshot builds, or event stream;
- a public arbitrary-SQL endpoint;
- broad JSONB indexing or a generic normalization-diff engine;
- preserving the old SQLite schema as an indefinite external compatibility
  contract.
