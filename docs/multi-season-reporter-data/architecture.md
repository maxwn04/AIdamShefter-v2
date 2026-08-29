# Multi-Season Reporter Data Architecture

## Review Outcome

The feature should proceed, but not with a preparation service that owns
lineage, freshness, refresh execution, selection, and snapshot construction.
That surface is shallow and difficult to reason about. The reviewed design uses
small public APIs backed by deep internal modules, makes preparation a bounded
state transition, and freezes every factual input before claiming a build.

The irreducible complexity is limited to two places: coalescing concurrent
refreshes and opening both version-2 and version-3 artifacts during migration.
Each is isolated behind one module and does not leak into generation or query
callers.

## Goals and Boundary

A generation for one competition season receives one immutable SQLite artifact
containing its primary season plus every lower-sequence season in the same
competition. Historical seasons are available to the model but are not loaded
into its context unless it calls a history tool or guarded SQL.

PostgreSQL remains preparation/build infrastructure. Reporter code never gets a
database session, Sleeper client, refresh service, or snapshot service. Core
competition-season lineage and roster mappings are authoritative. Raw,
hash-verified Sleeper responses are authoritative for snapshot facts.

## Public Surface

The caller-facing datalayer has three operations:

```python
prepared = DatalayerSnapshotPreparationService.get_or_create(request)
manual = DatalayerRefreshService.refresh(request)
data = FrozenLeagueData.open(prepared.snapshot)
```

`GenerationService` only maps a generation to `LIVE` or `READINESS_ONLY` and
calls the preparation facade. It does not know endpoint kinds, lineage rules,
freshness thresholds, roster-mapping rules, refresh keys, or build keys.

## Deep Internal Modules

### `snapshot_inputs.py`

```python
def resolve(request: PrepareSnapshotRequest) -> ResolutionState: ...

ResolutionState = (
    ResolvedSnapshotInputs
    | RefreshSeason
    | MapSeasonRosters
)
```

This module owns the complete meaning of “snapshot ready”: lineage, selected
League settings, season cutoffs, exact raw-request requirements, one eligible
candidate per scope, freshness, roster mappings, and `input_revision`. It
returns the oldest blocking season as one typed next state. It neither performs
network work nor builds an artifact.

### `refresh_coordination.py`

```python
def ensure(action: RefreshSeason) -> RefreshReceipt: ...
```

This module owns automatic refresh claim/join, bounded waiting, stale-claim
recovery, and delegation to the existing one-season refresh service. Manual
refresh remains independent. A refresh receipt is audit evidence; callers must
re-run input resolution rather than treating refresh status as proof of
readiness.

### `preparation_service.py`

The facade is intentionally small. It repeatedly resolves input state, performs
the single returned refresh action, and resolves again. It records attempted
season IDs and permits one automatic refresh attempt per season. A resolved
state is passed to the resolved snapshot builder; a repeated refresh need becomes
`SnapshotInputsUnavailable`; a mapping state becomes the existing actionable
mapping error.

This loop contains orchestration only. It does not calculate requirements,
freshness, revisions, or keys.

### `resolved_snapshot_builder.py`

```python
def get_or_create(inputs: ResolvedSnapshotInputs) -> ReadyDataSnapshot: ...
```

The builder owns build claim/reuse, exact payload loading, materialization,
artifact verification, and sealing. It never re-runs selection. A later refresh
or mapping correction creates a future input revision and cannot mutate the
build already claimed.

During transition, the existing request-based `DatalayerSnapshotService`
continues to build projection-version-2 artifacts for the active generation
path. `DatalayerResolvedSnapshotBuilder` is the only version-3 implementation
behind the preparation facade's `ResolvedSnapshotBuilder` protocol. Production
composition switches to that facade only after the version-3 runtime is ready;
the two input contracts are never combined with union dispatch.

### `snapshot_sqlite/*`

Projection, derivation, schema, insertion, and verification remain pure over
the frozen materialization input. They perform no API calls, candidate
selection, mapping heuristics, or PostgreSQL planning.

### `query/*`

`FrozenLeagueData.open` performs one version dispatch to a version-specific
reader. Curated query implementations operate on one stable schema contract;
version conditionals are not scattered through queries.

## Input Resolution

The resolver uses raw observations as its single source of Sleeper facts:

1. Read core lineage only: competition-season IDs, league IDs, years, sequence
   numbers, and whether the primary is the latest attached season.
2. Select the latest complete League response for every included season. The
   oldest missing League scope becomes `RefreshSeason`.
3. Normalize those selected League payloads into immutable
   `SnapshotSeasonSettings`.
4. Derive exact requirements from the frozen settings and per-season cutoffs:
   the requested week for the primary and week 18 for predecessors.
5. Fetch one latest complete eligible candidate per required scope in one
   batched resource operation.
6. Resolve roster payload IDs and compare them with exact core season-roster and
   franchise mappings. Missing later-season mapping becomes
   `MapSeasonRosters`; names, list position, and reused roster numbers are never
   guesses.
7. Apply readiness and freshness policy.
8. Freeze the selected manifest, mappings, season settings, and canonical
   `input_revision` in `ResolvedSnapshotInputs`.

The normalized PostgreSQL league head is not consulted during snapshot
planning. This eliminates drift between planning settings and the selected raw
League payload used for materialization.

## Refresh Policy

- Historical seasons, a non-latest primary, and backtests are readiness-only.
- The latest primary in `LIVE` mode refreshes when required input is missing or
  its oldest selected observation exceeds the configurable 15-minute default.
- The global player catalog is readiness-only.
- NFL state is not a version-3 snapshot requirement because no snapshot table
  or query consumes it. The ordinary refresh may still fetch it for normalized
  application state.
- A standard season refresh stays a full refresh. Endpoint-specific TTLs and
  partial refresh plans are deferred until measurements justify them.

The resolver always reports only the oldest blocking season. Re-resolution
after each action naturally gives oldest-first execution and prevents a stored
multi-action plan from becoming stale.

## Immutable Factual Identity

`input_revision`, not request identity or response time, determines whether the
artifact facts are equal. It hashes a canonical ordered representation of:

- each included season's competition-season ID, Sleeper league ID, year,
  sequence, role, and cutoff;
- each selected `(scope_key, response_sha256)` pair;
- each exact `(competition_season_id, sleeper_roster_id, season_roster_id,
  franchise_id)` mapping.

Selected League settings are covered by the selected League response hash.
Request IDs, refresh IDs, and timestamps remain audit metadata only.

The canonical build key contains primary season, cutoff, date, projection
version, and `input_revision`. Mapping corrections therefore produce a new
artifact even when Sleeper bytes are unchanged; identical refreshed bytes and
identical mappings reuse an existing artifact.

All referenced API responses, payloads, season identities, and mappings are
immutable records. The resolver freezes their IDs and hashes before the build
claim. There is no “manifest changed, retry” branch because the builder cannot
reselect a manifest.

## Version-3 Artifact

SQLite version 3 adds `snapshot_seasons` and fixes every single-season key
assumption:

- `users` is league-scoped;
- `franchise_id` may repeat across seasons and is unique only within a season;
- transactions and moves are keyed and joined with league identity;
- relevant indexes include league or season scope;
- metadata records `input_revision` and primary-season identity.

PostgreSQL persists explicit sealed snapshot-season membership and the same
`input_revision`. Sealing atomically records artifact identity, selected request
membership, season membership, and completeness information.

## Runtime and Model Access

Artifact open selects one version-specific reader after validating schema
markers, metadata, membership, season data, and roster identities. The public
facade and curated query modules do not branch on projection version; the reader
owns schema differences such as the version-3 league-scoped transaction-move
join. Existing curated calls default to the primary season, while optional
season selection resolves an immutable catalog scope before executing SQL.
`player_summary` remains global.

The runtime exposes a uniform season catalog. A retained version-2 artifact
synthesizes its single primary membership; a version-3 artifact exposes the
validated oldest-to-primary `snapshot_seasons` rows. Cross-season history calls
therefore degrade naturally to one-season results for retained artifacts rather
than introducing version-capability errors.

`franchise_history` accepts an exact franchise UUID or resolves a roster/team
reference inside the primary season first. It never performs loose-name matching
across all years. The resolved durable franchise ID is the only cross-season
join key; roster IDs, team names, manager names, and season-roster IDs are
reported as season-local attributes. Missing appearances are omitted and a
retained version-2 artifact naturally returns one primary appearance. Guarded
SQL remains SELECT-only, single-statement, allowlisted, and row-limited.

Reporter access remains primary-first and history is opt-in. Discovery and
curated history tools establish scope before any explicit-season drill-down.
The reporter's existing tool-call recorder is the historical evidence receipt;
the research brief references those calls with complete arguments instead of
introducing another provenance model.

## Failure Model

Expected preparation outcomes are values, not exceptions:

- `ResolvedSnapshotInputs`
- `RefreshSeason`
- `MapSeasonRosters`

Only boundary failures escape:

- `SnapshotInputsUnavailable`: a bounded refresh/re-resolution did not produce
  the exact required inputs;
- `RosterIdentityMappingRequired`: a human-owned cross-season identity mapping
  is absent;
- `RefreshUnavailable`: refresh claim, execution, or bounded joining failed;
- `DatalayerScopeConflict`: lineage, season, payload, or mapping identities
  contradict one another;
- `SnapshotArtifactInvalid`: a sealed or opened artifact disagrees with its
  schema, manifest, membership, hash, or revision.

There is no partial successful snapshot. Refresh completion does not define the
next state, names do not define identity, and concurrent writes do not mutate a
frozen input set. These choices remove recovery branches rather than adding
defensive handling throughout the stack.

## Readability Rules

- Domain states are immutable tagged models, not an enum plus optional fields.
- Every module has one reason to change and exposes the smallest useful method.
- Selection/resource queries return domain records, not ORM rows.
- Canonical ordering and hashing live beside `ResolvedSnapshotInputs`.
- Version compatibility branches once at artifact open.
- No base service, plugin registry, event bus, or generic workflow framework is
  introduced for this feature.
- Tests name the invariant being protected and use real SQLite artifacts for
  materialization/runtime behavior.

## Architecture Decisions

- One physical artifact enables reproducible cross-season joins.
- `sequence_number` defines lineage; year arithmetic does not.
- Complete-or-fail membership prevents omitted history from appearing absent.
- Historical cutoff is week 18; successful empty endpoint payloads represent
  leagues that ended earlier.
- History is opt-in at tool time, preserving ordinary report cost and behavior.
- Raw selected payloads are the only Sleeper authority for snapshot planning.
- Refresh work is one season at a time and always followed by re-resolution.
- Version-2 artifacts remain immutable and readable through isolated dispatch;
  new artifacts use version 3.

## Open Questions

None block initial implementation. Artifact size, build latency, and refresh
traffic should be measured before introducing a history-depth limit, partial
refresh execution, or endpoint-specific freshness policy.
