# Multi-Season Reporter Data Application Contracts

## Vocabulary and Ownership

| Term | Meaning | Owner |
| --- | --- | --- |
| Primary season | Generation season bounded by the requested week | Generation request |
| Historical season | Same-competition season with a lower sequence | Core lineage |
| Season settings | League rules decoded from the selected raw League payload | Input resolver |
| Resolved inputs | Complete frozen facts and identities for one build | Input resolver |
| Season membership | Sealed declaration that an artifact contains a season | Snapshot resource |
| Input revision | Hash of all facts and identity mappings that affect output | Resolved inputs |
| Franchise | Durable team identity across season rosters | Core roster mapping |

## Public Contracts

```python
class SnapshotPreparationMode(StrEnum):
    LIVE = "live"
    READINESS_ONLY = "readiness_only"

class PrepareSnapshotRequest(ContractModel):
    snapshot: SnapshotRequest
    mode: SnapshotPreparationMode
    requested_at: AwareDatetime

class PreparedSnapshot(ContractModel):
    snapshot: ReadyDataSnapshot
    refresh_receipts: tuple[RefreshReceipt, ...]
```

`GenerationService` selects a mode and calls
`DatalayerSnapshotPreparationService.get_or_create`. It does not construct a
refresh or requirement plan. Live generation uses `LIVE`; backtests use
`READINESS_ONLY`.

The external snapshot request remains primary-season based:

```python
SnapshotRequest(
    competition_season_id=primary_season_id,
    through_week=week_end,
    as_of_date=execution_date,
)
```

`ReadyDataSnapshot` and snapshot detail responses expose ordered
`included_seasons` and `input_revision`. Existing primary season and week fields
remain authoritative for default scoping and backward compatibility.

## Internal Resolution Contracts

Expected next states are different models, so invalid combinations cannot be
constructed:

```python
@dataclass(frozen=True)
class RefreshSeason:
    season: SnapshotSeasonIdentity
    through_week: int
    reason: Literal["missing", "stale"]
    missing_scopes: tuple[ScopeKey, ...]

@dataclass(frozen=True)
class MapSeasonRosters:
    season: SnapshotSeasonIdentity
    roster_ids: tuple[str, ...]

@dataclass(frozen=True)
class ResolvedSnapshotInputs:
    primary: SnapshotRequest
    seasons: tuple[ResolvedSnapshotSeason, ...]
    manifest: tuple[SelectedSnapshotRequest, ...]
    roster_mappings: tuple[ResolvedRosterMapping, ...]
    input_revision: str

ResolutionState = ResolvedSnapshotInputs | RefreshSeason | MapSeasonRosters
```

`ResolvedSnapshotInputs` is complete by construction. It has one primary season,
every predecessor, exact selected requests for all requirements, exact roster
mappings, frozen League settings, and a verified revision. It is the only input
accepted by `DatalayerResolvedSnapshotBuilder.get_or_create`. The existing
request-based `DatalayerSnapshotService` remains the version-2 compatibility
adapter until generation cutover; it is not widened to accept both contracts.

The resource layer supplies one batched operation that returns the latest
complete eligible observation for each requested scope. It does not load full
request history and does not perform one query per scope.

## Runtime Contracts

`FrozenLeagueData.open` validates the artifact and dispatches once to a
version-specific reader. Curated methods receive a resolved season scope and
contain no artifact-version branches. `SnapshotSeason` is an immutable query
value containing `competition_id`, `competition_season_id`,
`sleeper_league_id`, `season_year`, `sequence_number`, `role`, and
`through_week`. The uniform runtime surface includes:

```python
def available_seasons(self) -> tuple[SnapshotSeason, ...]: ...
def get_league_history(self) -> dict[str, Any]: ...
def get_franchise_history(self, franchise_or_primary_roster: str | int) -> dict[str, Any]: ...
```

Every season-scoped curated method gains keyword-only `season: int | None =
None`; `None` selects the primary season. `player_summary` stays snapshot-global.
Version-2 readers synthesize one primary `SnapshotSeason`; version-3 readers
validate their catalog against sealed membership and revision before any query.
Reporter tools mirror these contracts. Guarded SQL exposes the
version-specific allowlist, including `snapshot_seasons` for version 3.

`get_league_history` returns `found`, the competition and primary year, and an
oldest-to-primary `seasons` list. Each season entry contains its competition-
season and Sleeper league IDs, year, sequence, role, cutoff, league name, team
count, and standings at that cutoff.

`get_franchise_history` treats only a canonical UUID string as a direct durable
franchise lookup. Every other input is resolved against the primary season's
roster/team/manager identities before querying by `franchise_id`. A successful
result contains ordered appearances with season metadata, season-roster and
Sleeper roster identities, contemporaneous names, and the cutoff standing or
`None`. Seasons without an appearance are omitted. Missing and ambiguous
primary references remain ordinary `found: false` values; names are never
matched independently in historical seasons.

## Reporter Tool Contracts

The reporter exposes `available_seasons`, `league_history`, and
`franchise_history` as explicit discovery and curated-history tools. Every
season-scoped reporter tool accepts an optional four-digit `season`; omission
retains primary-season behavior. `player_summary`, history/discovery tools, and
`run_sql` remain snapshot-global.

Historical research is opt-in. The reporter discovers included years, prefers
curated history summaries, and adds explicit-season detail calls only when the
request, memory, or current facts create a material historical lead. Brief
source references retain the tool name and every material argument, including
the season year. A comparison, callback, record, or superlative requires frozen
evidence for every season involved. Historical names never establish durable
franchise identity independently; `franchise_history` performs the one allowed
primary-season resolution before following `franchise_id`.

Existing durable tool-call recording is the evidence receipt. It stores tool
name, implementation version, arguments, result, and status, so multi-season
access introduces no parallel evidence store.

## Generation Integration Contracts

New submissions persist generation-settings schema version 2. Its input policy
uses `automatic_missing_and_latest_live_freshness`, maps live generations to
`LIVE`, maps backtests to `READINESS_ONLY`, and derives the snapshot date from
the UTC execution date. Generation code chooses only that mode and delegates to
`DatalayerSnapshotPreparationService`.

Already-pending settings-version-1 generations retain the exact submitted
`never` policy and execute through the isolated version-2 snapshot adapter.
Reruns are new submissions and therefore use settings version 2. The two
snapshot interfaces remain separate dependencies; neither accepts a union of
request and resolved-input contracts.

Every newly started generation writes manifest schema version 2. Its snapshot
input contains the primary season, optional factual `input_revision`, ordered
oldest-to-primary season coverage, preparation mode, and ordered automatic
refresh receipts. A receipt records its claim, refresh run, affected season,
cutoff, terminal status, and claimed/joined disposition. Coverage is nonempty,
unique, ordered, has exactly one matching final primary, and gives every
historical season cutoff 18. Receipts must reference an included season at the
same cutoff. Existing stored manifests are never rewritten.

## Operator Readiness Contracts

Snapshot readiness is a network-free projection of
`SnapshotInputResolver.resolve()`. It returns exactly one tagged state:

- `ready` carries the factual `input_revision` and complete ordered
  oldest-to-primary season coverage;
- `refresh_required` carries the affected season, cutoff, reason, and missing
  endpoint scopes;
- `roster_mapping_required` carries the affected season and exact unmapped
  Sleeper roster IDs.

`GET .../snapshot-readiness` only inspects those states. It never claims a
refresh, fetches Sleeper data, builds an artifact, or persists a snapshot.
`POST .../snapshot-preparations` invokes the existing bounded preparation
facade with server UTC as both request time and snapshot date. The response
contains the ready version-3 snapshot and ordered automatic-refresh receipts.
Both endpoints accept the same explicit cutoff and `LIVE` or
`READINESS_ONLY` mode, so operator inspection and generation preparation share
the resolver's requirement and freshness policy.

Snapshot audit summaries expose nullable `input_revision`, ordered sealed
season membership, artifact digest, and byte length. They never expose storage
keys or source payload bodies. Mapping requirements and scope conflicts are
structured conflicts; unresolved inputs and refresh availability are
structured service-unavailable responses with only safe stable identifiers;
artifact validation failures are sanitized internal failures.

The generation form keys readiness by competition, primary season, week end,
and preparation mode. `ready` and `refresh_required` permit submission because
generation owns the same bounded preparation; only the latter offers an
explicit **Prepare now** action. `roster_mapping_required`, loading, failed, or
unknown readiness blocks submission. Mapping links use the returned
competition-season ID rather than resolving a historical name. Preparation
invalidates readiness, refresh history, snapshot audit, season overview, and
roster-mapping queries for every season named by a receipt or structured
failure.

## Invariants

- Included seasons are exactly the primary plus all lower-sequence seasons in
  one competition, ordered oldest to primary.
- Exactly one membership is primary and matches the snapshot row and request.
- Historical cutoffs are week 18; the primary cutoff is the requested week.
- Season year, competition-season ID, and Sleeper league ID are unique within a
  snapshot.
- Snapshot settings and requirements derive from the selected raw League
  payload, never from a mutable normalized head.
- Every requirement has exactly one eligible complete selected request.
- Every included roster has exactly one season-roster and franchise mapping.
  A franchise may correctly recur in different seasons.
- The manifest, mappings, and season identities are frozen before a build is
  claimed; the builder never reselects them.
- `input_revision` is identical in resolved inputs, build key, PostgreSQL ready
  row, artifact metadata, and sealed membership audit.
- SQLite keys and joins remain collision-safe when Sleeper reuses user, roster,
  matchup, week, or transaction identifiers across leagues.
- Existing curated calls without `season` retain primary-season shapes and
  semantics.
- Artifact metadata, SQLite season rows, PostgreSQL membership, artifact hash,
  and ready snapshot identity agree before open succeeds.

## Input Revision Contract

The revision hashes canonical JSON containing ordered season identity/cutoff,
ordered scope/payload-hash pairs, and ordered exact roster mappings. Request IDs,
refresh IDs, observation times, and build times are audit metadata and do not
affect factual identity.

Consequences:

- changed Sleeper bytes create a new revision;
- a roster-to-franchise correction creates a new revision even with unchanged
  Sleeper bytes;
- identical payloads and mappings reuse the same artifact;
- a concurrent later refresh affects only a future resolution.

## Errors Defined at Boundaries

Expected missing/stale/mapping conditions remain `ResolutionState` values.
Only these boundary errors are public:

| Error | Meaning |
| --- | --- |
| `SnapshotInputsUnavailable` | One bounded refresh attempt did not produce exact required input |
| `RosterIdentityMappingRequired` | Human-owned durable identity mapping is missing |
| `RefreshUnavailable` | Automatic refresh could not be claimed, joined, or completed |
| `DatalayerScopeConflict` | Lineage, scope, payload, or mapping identities contradict |
| `SnapshotArtifactInvalid` | Built/opened artifact disagrees with schema, membership, hash, or revision |

Errors identify the affected season and stable resource IDs. They do not expose
raw payload bodies or encourage callers to infer the next action from prose.
Curated invalid season/week inputs remain ordinary boundary validation errors
translated by the reporter tool adapter.

## Lifecycle

Snapshot states remain `building -> ready|failed` and `ready -> expired`.
Request membership, season membership, artifact hash, and revision seal in one
transaction. One active build exists per canonical key.

Equivalent automatic refreshes share one durable active key. A waiter observes
the receipt and resolves inputs again. Manual refreshes are not suppressed.
Automatic preparation permits at most one refresh attempt for a season in one
call, preventing unbounded repair loops.

## Compatibility and Transition

1. Add lineage/candidate reads, season membership, input revision, and automatic
   refresh coordination without changing generation behavior.
2. Add the closed resolver states and preparation facade behind focused tests.
3. Add version-3 projection/materialization consuming only resolved inputs.
4. Add a single version-2/version-3 runtime dispatch and version-3 queries.
5. Add reporter tools and generation policy version 2. Pending policy-version-1
   generations keep their submitted `never` semantics; reruns are new requests.
6. Activate version 3 only after mapping readiness and compatibility gates pass.
7. Never rewrite old artifacts or manifests.

The legacy `datalayer/` facade may remain single-season. The implementation
target is the backend application stack.

## Acceptance Coverage

| Behavior | Focused coverage |
| --- | --- |
| Lineage includes all and only predecessors | Core lineage resource tests |
| Raw League payload controls settings/requirements | Resolver tests with normalized-head drift |
| Missing inputs return the oldest refresh state | Resolver state tests |
| Ready history is not age-refreshed | Clocked resolver tests |
| Only stale latest live primary refreshes | Clocked preparation integration test |
| Backtest never age-refreshes | Generation mode test |
| Repeated season need terminates | Preparation bounded-loop test |
| Equivalent preparations join one refresh | Refresh coordination test |
| Partial refresh is followed by exact re-resolution | Resolver/coordination test |
| Missing later-season mapping is actionable | Roster mapping test |
| Mapping correction changes revision | Input-revision test |
| Concurrent later refresh cannot alter claimed input | Snapshot service test |
| Multi-season identifier reuse does not collide | Real version-3 SQLite fixture |
| Primary default and explicit history both work | Version-3 runtime tests |
| Version dispatch does not leak into queries | Version-2/version-3 contract tests |
| Guarded SQL joins seasons through franchise ID | Real SQLite guarded-SQL test |
| Artifact/DB membership disagreement is rejected | Snapshot open/seal tests |
| Model can discover history without mandatory use | Reporter tool/procedure tests |
