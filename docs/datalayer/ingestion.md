# Datalayer Ingestion and Normalization

## Invariants

The ingestion design is governed by these rules:

1. Record the source attempt before attempting to change normalized facts.
2. A failed or incomplete response never erases the current normalized scope.
3. A successful complete empty response is authoritative and can erase the
   prior rows for that scope.
4. Request start time, with request ID as a tiebreaker, orders competing heads.
5. Normalization of one endpoint scope and advancement of its head are atomic.
6. Every normalized current row points to the request that supplied it.
7. Normalizers are deterministic, side-effect free, and reusable for snapshot
   replay.
8. Exact fantasy values enter the application as `Decimal`, never binary float.

## Refresh Sequence

```mermaid
sequenceDiagram
    participant Caller
    participant Service as DatalayerRefreshService
    participant Data as SleeperDataManager
    participant Source as SleeperSourceClient
    participant Endpoint as Endpoint-family module
    participant DB as PostgreSQL

    Caller->>Service: refresh(RefreshRequest)
    Service->>Data: start_refresh(...)
    Data->>DB: insert running refresh
    Service->>Service: build explicit endpoint plan
    loop each endpoint request
        Service->>Source: execute(request)
        Source-->>Service: SourceAttempt result
        alt failed source attempt
            Service->>Data: record_attempt(failure, incomplete finding)
            Data->>DB: insert failed request
        else parsed successful response
            Service->>Endpoint: validate completeness(payload, request)
            Endpoint-->>Service: CompletenessFinding
            Service->>Data: record_attempt(response, payload receipt, finding)
            Data->>DB: insert request and deduplicate payload
            alt incomplete response
                Note over Service,Data: retained for audit; current scope is unchanged
            else complete response
                Service->>Endpoint: normalize(payload, domain context)
                alt normalization rejected
                    Service->>Data: reject_normalization(request ID, reason)
                else normalized
                    Endpoint-->>Service: EndpointRecords
                    Service->>Data: apply_scope(request ID, records)
                    Data->>DB: compare head, replace scope, advance head
                end
            end
        end
    end
    Service->>Data: finish_refresh(refresh ID)
    Data->>DB: derive and persist counts/status
    Service-->>Caller: RefreshOutcome
```

Endpoint requests may execute concurrently with bounded concurrency, but each
attempt is recorded and each normalized scope commits independently. A partial
failure does not roll back unrelated successful scopes.

Fetch concurrency does not imply arbitrary apply order. The refresh service
applies complete records in an explicit dependency order required by the
relational model:

1. league metadata, league users, and the global player catalog;
2. rosters, managers, current roster players, and seeded draft-pick coordinates;
3. weekly matchups/player performances, transactions/moves, traded-pick
   ownership, and bracket nodes.

An unmet dependency produces a structured normalization rejection for that
scope; it is never retried by accidentally holding a database transaction open
across another endpoint. Independent scopes at the same level may still apply
concurrently when manager transactions remain short.

## Endpoint-Family Ownership

Provider-facing knowledge lives in one explicit module per endpoint family.
Each module owns request construction, deterministic scope construction,
response completeness validation, and raw normalization. There is no separate
endpoint, completeness, or normalizer registry.

Initial endpoint kinds:

| Endpoint kind | Scope | Current target | Snapshot use |
| --- | --- | --- | --- |
| `league` | competition season | league state | Required metadata |
| `league_users` | competition season | users + league users | Required names/managers |
| `league_rosters` | competition season | rosters/managers/current players | Required roster state and profiles |
| `nfl_state` | global sport | observation only | Season/week provenance |
| `player_catalog` | global sport | player catalog | Required player resolution |
| `matchups` | season + week | matchups + player performances | Required for every included week |
| `transactions` | season + week | transactions + moves | Required even when empty |
| `traded_picks` | competition season | draft-pick current view | Required when draft rounds exist |
| `winners_bracket` | season + bracket kind | playoff bracket | Conditional |
| `losers_bracket` | season + bracket kind | playoff bracket | Conditional |

Refresh planning owns what to fetch. Snapshot selection owns which scopes a
snapshot requires. Persistence projection owns where endpoint records are
stored. They share `EndpointKind` and `ScopeKey` values but do not duplicate
provider parsing rules. An ordinary explicit dispatch by endpoint kind keeps
the path discoverable.

## Source Response Capture

The source client returns a discriminated result rather than raising away audit
information or forcing callers to interpret a mostly-optional response object:

```python
class SuccessfulSourceAttempt(BaseModel, frozen=True):
    outcome: Literal["succeeded"] = "succeeded"
    endpoint: EndpointRequest
    requested_at: datetime
    completed_at: datetime
    http_status: int
    latency_ms: int
    payload: JsonValue
    raw_sha256: str
    byte_length: int
    media_type: str


class FailedSourceAttempt(BaseModel, frozen=True):
    outcome: Literal["failed"] = "failed"
    endpoint: EndpointRequest
    requested_at: datetime
    completed_at: datetime
    status: Literal["http_error", "transport_error", "invalid_payload"]
    http_status: int | None
    latency_ms: int
    error: SanitizedSourceError


SourceAttempt = Annotated[
    SuccessfulSourceAttempt | FailedSourceAttempt,
    Field(discriminator="outcome"),
]
```

Transport exceptions are converted into `transport_error` envelopes. HTTP error
bodies are sanitized and recorded in the request error shape; they are not
eligible payloads. Invalid JSON becomes `invalid_payload`. Secrets, headers,
environment values, and arbitrary exception representations are never stored.

After successful JSON parsing, payload hashing uses the canonical JSON encoding
defined by the datalayer (UTF-8, stable object-key order, compact separators),
not a pretty-printed or provider-whitespace-dependent representation. Inline
JSONB and locally file-stored canonical bytes therefore verify against the same
hash. The local file store verifies large payload writes before
`record_attempt()` references them.

The source parser constructs fractional JSON numbers as `Decimal`; binary float
never precedes fantasy-value normalization. Canonical encoding renders those
decimals as JSON numbers with insignificant zeros removed. Inline JSONB writes
use the canonical JSON text at the PostgreSQL boundary, and reads used for
replay return canonical text for Decimal-first parsing and hash verification.

## Completeness

Completeness answers “is this response authoritative for its requested scope?”
It is deliberately distinct from success and from non-emptiness.

Examples:

- `[]` for Week 8 transactions is successful and complete;
- an HTML 200 response is invalid, not a complete empty response;
- a roster list whose league identity cannot be reconciled is complete source
  data but blocked from normalization by identity mapping;
- a truncated or malformed player catalog is retained but incomplete;
- a bracket request made before Sleeper has created a bracket may be complete
  and empty when the endpoint contract says so.

Completeness findings are persisted as `is_complete` and a safe reason. The
request remains available for audit even when it cannot be normalized or
selected into a snapshot.

For a parsed successful response, the endpoint-family module determines
completeness before `record_attempt()` so the finding is stored with the source
observation. A failed source attempt is recorded with a standard incomplete
finding owned by the refresh service. If a completeness validator itself fails
unexpectedly, the service still records the attempt as incomplete with a
sanitized internal validation code, then reports that scope as failed. It never
guesses that an unvalidated response is authoritative.

## Endpoint Records

Normalization returns endpoint-specific domain records without workflow
metadata. Request ID, scope key, observation timestamps, hashes, and version
remain on the recorded `ApiRequest` and selected-request manifest.

Legacy row dataclasses are reused only when they are already a natural record
for the new consumers. Otherwise, the existing calculation is extracted into a
new endpoint record rather than surrounded by provenance and sink adapters.
Pydantic validation is added at new or changed application boundaries where
PostgreSQL intentionally does not own semantic validation.

Normalizers may use small pure parsing/derivation helpers shared within endpoint
families. They may not:

- query current PostgreSQL state;
- open SQLite;
- construct ORM rows;
- resolve names through a database connection;
- drop malformed records without a structured rejection/warning;
- infer durable core identities from display names.

## Identity Inputs

The service resolves these values before normalizing competition-scoped data:

```python
class SeasonIdentityMap(BaseModel, frozen=True):
    competition_id: UUID
    competition_season_id: UUID
    sleeper_league_id: str
    season_year: int
    roster_by_sleeper_id: Mapping[str, SeasonRosterIdentity]
```

The map comes from the core identity boundary. It maps provider IDs to stable
season-roster/franchise IDs but does not expose ORM objects.

The first league/users/rosters observations may be captured during competition
setup before all roster mappings exist. Those requests remain valid source
history. `services/league/mapping_service.py` establishes mappings, after which a
maintenance command can reapply the already captured roster request. The
datalayer never silently creates a franchise based only on array position or
manager name.

## Atomic Scope Application

`SleeperDataManager.apply_scope()` follows this transaction:

1. load the recorded request and lock its `normalized_scopes` row;
2. verify the source request is successful, complete, payload-hash verified,
   and consistent with the endpoint records;
3. compare request start time and request ID against the current head;
4. return `stale_ignored` if the incoming request is older;
5. return `already_applied` for the same request;
6. if the response hash matches the head, advance only observation/head
   provenance and return `identical_head_advanced`;
7. otherwise replace/upsert exactly that complete scope inside the manager;
8. update request normalization status/version/time and advance the scope head;
9. commit once.

An identical newer response does not rewrite current rows. Those rows may retain
the earlier request ID that supplied identical content, while the head proves a
newer observation occurred.

### Scope replacement examples

- Matchups and player performances replace one season/week scope.
- Transactions and moves replace one season/week scope, including deletion to
  zero rows for an authoritative empty response.
- League users replace one competition-season users scope, while global user
  profiles upsert by Sleeper user ID.
- The player catalog upserts observed players and does not delete players that
  disappear from a later catalog.
- Roster managers and current roster players replace one season's roster scope.
- Bracket nodes replace one season/bracket-kind scope.

The internal projection for each endpoint kind is explicit and tested; there is
no cross-resource write helper, generic JSON diff, or generic CRUD repository.

`sleeper.users` is global even though user observations arrive through
competition-season scopes. Its upsert compares the incoming request's
`(requested_at, request_id)` with the request that supplied the existing global
row; an older observation from another league cannot roll a newer global user
profile backward. Any future normalized table written by more than one scope
must define the same cross-scope ordering invariant rather than relying only on
the per-scope head.

## Refresh Status

Refresh finalization derives status from recorded request results:

- `succeeded`: every required planned request succeeded and normalized or was
  safely recognized as an identical/stale observation;
- `partial`: at least one scope succeeded and at least one required scope
  failed, was incomplete, or needs identity mapping;
- `failed`: no required scope completed successfully or a refresh-level
  invariant prevented useful work;
- `cancelled`: caller cancellation stopped remaining requests;
- `running`: non-terminal only.

Optional failures are retained and summarized but do not necessarily make the
refresh partial. `finish_refresh()` derives counts and status from the child
request outcomes inside the manager transaction rather than trusting a caller-
supplied summary.

`RefreshRun.endpoint_scope` stores the ordered plan as scope key, endpoint kind,
requiredness, and dependency keys. Finalization groups retry attempts by planned
scope and uses its latest terminal attempt. A required planned scope with no
attempt is failed unless the run was cancelled, in which case it is counted as
not attempted and the aggregate remains `cancelled`. Public outcome counts are
scope counts; raw request-attempt counts remain audit metadata.

## Retries

Each HTTP attempt is an `api_requests` row. A bounded retry therefore creates a
new request with the same scope key and its own timing, status, error, and
payload reference. The source client executes exactly one attempt; retry policy
lives in the refresh executor, which records an outcome before deciding whether
to try again.

Maintenance reprocessing does not create an API request. It updates
normalization status for the existing request and may advance the scope head
only through the same eligibility transaction.

## Current-View Read Models

`SleeperDataManager` returns resource objects designed for product display and
cross-season application workflows. They may join normalized Sleeper tables to
core competition/franchise identities, but they do not expose source ORM rows.

These reads clearly describe themselves as current observations. They must not
accept a historical week and then filter latest rows as if doing so recreated
historical knowledge. Historically bounded facts always go through a data
snapshot.
