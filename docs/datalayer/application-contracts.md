# Datalayer Application Contracts

## Contract Layers

The datalayer exposes different contracts to different callers. They must not be
collapsed into one universal facade.

| Caller | Contract | Why |
| --- | --- | --- |
| Frontend/operator | HTTP data routes | Validation, authorization, polling, and stable JSON |
| Generation/worker services | Refresh and snapshot services | Explicit workflows with typed inputs and outcomes |
| Resource-oriented routes | Context-scoped managers | Narrow current-state and audit reads |
| Reporter | `FrozenLeagueData` | Read-only curated facts and guarded SQL from one snapshot |

The examples below define shape and responsibility. Exact import names may be
adjusted during implementation, but the semantic fields and boundaries should
remain stable.

## Workflow Value Objects

Workflow inputs are immutable Pydantic values under
`backend/services/datalayer/contracts.py`. They are not persisted resource
objects or HTTP schemas.

### Refresh specification

```python
class RefreshTrigger(str, Enum):
    MANUAL = "manual"
    GENERATION = "generation"
    SCHEDULED = "scheduled"
    BACKFILL = "backfill"


class RefreshRequest(BaseModel, frozen=True):
    competition_season_id: UUID
    through_week: int | None
    trigger: RefreshTrigger
```

The service derives `competition_id` and the standard endpoint set. V1 always
fetches the player catalog and both bracket endpoints in its fixed base plan;
snapshot selection, not refresh callers, decides whether a bracket observation
is relevant to a historical artifact. Ordinary callers cannot partially
configure a refresh into an invalid data state. A future endpoint-specific
maintenance command is separate from the product refresh contract.

### Refresh outcome

```python
class ScopeRefreshResult(BaseModel, frozen=True):
    scope_key: ScopeKey
    api_request_id: UUID
    fetch_status: RequestStatus
    normalization_status: NormalizationStatus
    changed_current_view: bool
    warning_codes: tuple[str, ...] = ()


class RefreshOutcome(BaseModel, frozen=True):
    refresh_run_id: UUID
    status: RefreshStatus
    requested_scope_count: int
    succeeded_scope_count: int
    failed_scope_count: int
    scope_results: tuple[ScopeRefreshResult, ...]
```

A partial refresh is a successful workflow outcome with `status="partial"`, not
an exception. Failure to create or finalize the refresh aggregate is an
exception.

### Snapshot request

```python
class SnapshotRequest(BaseModel, frozen=True):
    competition_season_id: UUID
    through_week: int
    observed_through: datetime
```

This contract describes factual availability rather than generation intent.
The generation service converts live, historical replay, or retrospective
policy into a valid week/observation pair. Competition identity is derived from
the season. Missing required data always fails an ordinary snapshot request;
incomplete diagnostic builds are not part of this API.

V1 intentionally does not expose an instant-based domain cutoff. Matchups,
transactions, standings, and lineup reconstruction are week-scoped, and the
system has no trustworthy intra-week projection contract yet. Add an instant
variant only with explicit service-owned resolution and intra-week rules.

### Ready snapshot

```python
class ReadyDataSnapshot(BaseModel, frozen=True):
    id: UUID
    competition_id: UUID
    primary_competition_season_id: UUID
    through_week: int
    observed_through: datetime
    build_key: str
    selected_request_set_sha256: str
    snapshot_projection_version: str
    artifact: VerifiedLocalArtifact
    completeness_warnings: tuple[CompletenessWarning, ...]
```

The artifact value carries the verified local path/hash inside the backend. API
responses do not return filesystem paths or relative storage keys.

### Persistence alignment before implementation

The existing `sleeper.data_snapshots` baseline receives these focused schema
refinements before this service is implemented:

- add `build_key` plus a partial unique constraint allowing only one active
  `building` or `ready` row per key;
- remove snapshot `mode`; live/backtest/retrospective intent belongs to the
  generation rather than factual identity;
- consolidate materializer/schema versions into one
  `snapshot_projection_version` and add sanitized failure metadata;
- pin `response_sha256` beside every selected request ID and scope key;
- permit only the one-way `ready` to `expired` retention transition while
  keeping sealed meaning and membership immutable.

V1 populates `domain_cutoff_week` and leaves `domain_cutoff_at` null. The latter
remains a future schema seam, not a capability claimed by the Python contract.

## Service Interfaces

### Refresh service

```python
class DatalayerRefreshService:
    def refresh(self, request: RefreshRequest) -> RefreshOutcome: ...
```

`refresh()` is used by manual synchronization, scheduled refresh, and the
generation input workflow. Reprocessing a recorded request after a code or
identity correction is a maintenance command, not a second public service mode.

The service accepts these constructor dependencies:

- `SleeperSourceClient`;
- `SleeperDataManager`;
- configured `LocalDatalayerFileStore` for raw payloads too large for inline
  PostgreSQL JSONB;
- inline-payload threshold, code version, and normalizer version policy.

The deep manager resolves season/core identity as part of its aggregate API;
there is no one-method identity adapter or caller-supplied clock at the service
boundary.

Endpoint planning and endpoint-family dispatch are ordinary module functions,
not injected registries or one-method strategy objects.

### Snapshot service

```python
class DatalayerSnapshotService:
    def get_or_create(self, request: SnapshotRequest) -> ReadyDataSnapshot: ...
```

`get_or_create()` selects the exact request set, computes the canonical build
key, and atomically returns or builds the one matching snapshot. Callers cannot
bypass reuse or request a weakened incomplete build.

The service accepts:

- `SleeperDataManager` for eligible request reads and payload resolution;
- `DataSnapshotManager` for atomic build-key ownership, lifecycle, and
  membership;
- the SQLite materializer;
- configured `LocalDatalayerFileStore`;
- module-level projection/build metadata.

The service calls pure request-selection and endpoint-family functions directly;
they do not become injectable wrapper objects merely to make tests mock them.

### Generation-service use

The generation service composes the datalayer but remains the owner of
generation policy:

```python
snapshot = datalayer_snapshot_service.get_or_create(
    SnapshotRequest(
        competition_season_id=request.competition_season_id,
        through_week=request.domain_cutoff_week,
        observed_through=request.knowledge_cutoff_at,
    )
)

generation_manager.start(
    generation_id=request.id,
    data_snapshot_id=snapshot.id,
    # memory input, cutoffs, and complete manifest are supplied here too
)
```

The datalayer never mutates the generation row. It returns a ready snapshot
whose identity the generation service atomically pins with the other inputs.

## Resource Manager Contracts

All managers are constructed with a `ManagerContext`. Competition-scoped
operations apply that context to every read and write. Signatures below omit
ordinary pagination values for clarity.

### `SleeperDataManager`

```python
class SleeperDataManager:
    def get_season_identity_map(self, season_id: UUID) -> SeasonIdentityMap: ...
    def start_refresh(self, command: StartRefresh) -> RefreshRun: ...
    def expand_refresh_plan(self, refresh_id: UUID, command: ExpandRefreshPlan) -> RefreshRun: ...
    def record_attempt(self, command: RecordApiAttempt) -> ApiRequest: ...
    def apply_scope(
        self,
        request_id: UUID,
        records: EndpointRecords,
    ) -> ApplyResult: ...
    def reject_normalization(self, request_id: UUID, rejection: Rejection) -> ApiRequest: ...
    def finish_refresh(
        self,
        refresh_id: UUID,
        *,
        cancelled: bool = False,
        failure: RefreshFailure | None = None,
    ) -> RefreshRun: ...

    def get_refresh(self, refresh_id: UUID) -> RefreshRun: ...
    def list_refresh_requests(self, refresh_id: UUID) -> Page[ApiRequest]: ...
    def list_snapshot_candidates(self, query: SnapshotCandidateQuery) -> tuple[ApiRequestCandidate, ...]: ...
    def resolve_verified_payloads(self, request_ids: Collection[UUID]) -> tuple[VerifiedPayload, ...]: ...

    def get_season_overview(self, season_id: UUID) -> LeagueSeasonOverview: ...
    def get_roster(self, season_roster_id: UUID) -> SeasonRosterState: ...
    def list_matchups(self, season_id: UUID, week: int) -> tuple[Matchup, ...]: ...
    def list_transactions(self, query: TransactionQuery) -> tuple[Transaction, ...]: ...
    def search_players(self, query: PlayerSearch) -> Page[Player]: ...
```

`record_attempt()` content-addresses a successful payload and records the
request plus its completeness finding in one transaction. Successful parsed
responses are validated by the owning endpoint-family module before this call;
failed source attempts carry the refresh service's standard incomplete finding.
Large payload bytes are hash-verified and stored by the refresh service through
the local file store before this call. The manager validates and deduplicates
the supplied immutable receipt metadata; it performs no filesystem or network
I/O. When snapshot replay resolves that receipt, the file store verifies the
actual local bytes again.

`apply_scope()` owns the compare-and-swap request/head/current-view transaction
across the Sleeper persistence namespace. `finish_refresh()` derives status and
counts from recorded request outcomes; the service does not calculate and pass
the same summary back down.

Singular `get_*` methods either return the scoped resource or raise the common
resource-not-found error. Normal absence uses empty list/page results or a
specifically named search operation; callers are not forced to repeatedly
interpret `None`.

### `DataSnapshotManager`

```python
class DataSnapshotManager:
    def begin_or_get(self, command: BeginSnapshotBuild) -> SnapshotBuildState: ...
    def seal_ready(self, snapshot_id: UUID, command: SealSnapshot) -> ReadyDataSnapshot: ...
    def mark_failed(self, snapshot_id: UUID, failure: SnapshotFailure) -> DataSnapshot: ...
    def fail_stale_build(self, build_key: str, stale_before: datetime) -> bool: ...
    def expire_unusable(self, snapshot_id: UUID, reason: ArtifactFailure) -> DataSnapshot: ...
    def get(self, snapshot_id: UUID) -> DataSnapshot: ...
    def list_requests(self, snapshot_id: UUID) -> tuple[SnapshotRequestMembership, ...]: ...
```

`begin_or_get()` owns the uniqueness race for the canonical build key and
returns an explicit existing-ready, existing-building, or newly-claimed state.
Only `building` and `ready` rows participate in the partial unique constraint;
failed and expired attempts remain as history but do not prevent a later claim.
`fail_stale_build()` is an atomic compare-and-transition and is a no-op when the
matching build is no longer stale. `expire_unusable()` releases a ready build
whose artifact is missing or fails verification. These lifecycle operations
keep retry and recovery decisions out of callers and preserve the failed or
expired row for audit.
`seal_ready()` owns one transaction that validates current build state, inserts
the exact request membership, and records hashes, sizes, versions, warnings,
artifact key, and completion time. Ready input fields are immutable thereafter.

## Reporter Data Contract

The reporter uses the concrete `FrozenLeagueData` runtime. It preserves the
existing curated query categories—league/week, teams/rosters, players,
transactions, playoffs, and guarded SQL—without duplicating the full facade as
a one-implementation protocol.

The runtime adds context-manager lifecycle:

```python
with FrozenLeagueData.open(local_verified_snapshot) as data:
    reporter.run(data=data)
```

`DatalayerSnapshotService.get_or_create()` returns a verified local artifact.
The runtime validates its internal projection metadata and opens SQLite in
immutable read-only mode without exposing the connection to callers.

Convenience pairs such as games/games-with-players may remain distinct public
tool operations, while sharing one internal query implementation where doing so
removes duplicated SQL. Snapshot-relative naming should be explicit:
`get_roster_at_cutoff()` replaces the ambiguous `get_roster_current()`.

Reporter tool definitions stay in `services/reporter/tools/`. Tool handlers
delegate to `FrozenLeagueData`; the datalayer does not import reporter code.

## HTTP API

Routes use versioned JSON under `/api/v1`. The initial surface is intentionally
small.

### Refresh workflow

```text
POST /api/v1/competitions/{competition_id}/seasons/{season_id}/data-refreshes
GET  /api/v1/competitions/{competition_id}/data-refreshes/{refresh_id}
GET  /api/v1/competitions/{competition_id}/data-refreshes/{refresh_id}/requests
```

The POST body contains only an optional `through_week`; the service derives the
endpoint plan. V1 executes synchronously and returns `200 OK` with the terminal
resource. A later worker boundary may add `202 Accepted`, but the route does not
claim asynchronous dispatch until that worker exists. The URL season and body
are checked against manager scope.

### Current data reads

```text
GET /api/v1/competitions/{competition_id}/seasons/{season_id}/data/overview
GET /api/v1/competitions/{competition_id}/seasons/{season_id}/data/matchups?week=8
GET /api/v1/competitions/{competition_id}/seasons/{season_id}/data/transactions?week_from=1&week_to=8
GET /api/v1/competitions/{competition_id}/seasons/{season_id}/data/rosters/{season_roster_id}
GET /api/v1/players?query=mahomes&limit=20&cursor=...
```

These endpoints return typed API projections from current-view resource
objects. They are for product display, not generation inputs and not a remote
version of the reporter's arbitrary SQL tool.

### Snapshot audit

```text
GET  /api/v1/competitions/{competition_id}/data-snapshots/{snapshot_id}
GET  /api/v1/competitions/{competition_id}/data-snapshots/{snapshot_id}/requests
```

Ordinary generation requests resolve snapshots through `GenerationService`;
there is no separate public build/bypass route. Snapshot JSON exposes hashes,
cutoffs, status, warnings, and selected request metadata but never raw payload
bodies or private storage keys.

## HTTP Error Translation

| Application result/error | HTTP behavior |
| --- | --- |
| Missing scoped resource | `404` |
| Scope or identity mismatch | `409` |
| Invalid cutoff/specification | `422` |
| Required snapshot inputs unavailable | `409` with structured missing scopes |
| Sleeper refresh completed partially | Success response with `status="partial"` |
| Sleeper unavailable during refresh | Terminal failed/partial refresh resource; the source error is not re-raised to the route |
| Snapshot verification/internal invariant failure | `500` with sanitized correlation ID |

Reporter `found=false` results are not mapped through this table because they
are tool-domain results, not HTTP workflow failures.

## Composition

`backend/composition.py` constructs concrete managers, services, source clients,
the local datalayer file store, and clocks. Routes and workers request typed
factories/dependencies. No code resolves the datalayer from a
mutable global registry, and tests replace dependencies at the constructor or
FastAPI dependency boundary.
