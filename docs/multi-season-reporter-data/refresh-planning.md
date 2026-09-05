# Multi-Season Refresh Planning

## Purpose

Generation preparation makes every included season snapshot-ready without
routinely re-fetching completed history. Established competitions normally
refresh only a stale or missing current season. New competitions naturally walk
missing seasons oldest-first.

## Ownership

- `GenerationService` chooses only `LIVE` or `READINESS_ONLY`.
- `SnapshotInputResolver` decides the one next state from durable evidence.
- `RefreshCoordinator` claims or joins one automatic season refresh.
- `DatalayerRefreshService` executes the existing full one-season refresh.
- `DatalayerSnapshotPreparationService` runs the bounded resolve/act loop.
- `DatalayerResolvedSnapshotBuilder` consumes already-resolved immutable inputs.

The request-based `DatalayerSnapshotService` remains the isolated version-2
generation adapter until the version-3 runtime and generation cutover. It does
not share an overloaded input surface with the resolved builder.

No module owns both policy calculation and network execution.

## One Resolver, One Next Action

The resolver returns exactly one of:

```python
ResolvedSnapshotInputs | RefreshSeason | MapSeasonRosters
```

It always returns the oldest blocking season. The preparation facade performs a
`RefreshSeason`, records that season as attempted, then resolves from scratch.
It never stores or executes a list of future actions. This removes stale plans
when refresh results, mappings, or concurrent observations change.

`MapSeasonRosters` stops automatic work and raises the existing actionable
mapping boundary. A repeated `RefreshSeason` for an already-attempted season
raises `SnapshotInputsUnavailable`. Thus the loop is finite without a generic
retry counter.

## Exact Requirement Resolution

Resolution is two-phase because League payloads define later requirements:

1. Read immutable core lineage without normalized league settings.
2. Select a complete League observation per season; missing League input is the
   first refresh need.
3. Decode those payloads into frozen season settings.
4. Build exact scopes for each cutoff.
5. Read the latest complete candidate for every scope in one batch.
6. Verify exact roster/franchise mappings.
7. apply readiness and freshness policy.

The candidate read is shaped as “latest complete candidate per requested
scope.” It must not load all historical requests or issue N+1 scope queries.
Normalized scope heads may support application reads but are not readiness
proof for a replay-based snapshot.

Version 3 requires League, users, rosters, picks, relevant weekly matchups and
transactions, brackets, and the global player catalog. NFL state is omitted
because version-3 projection does not materialize or query it.

## Decision Policy

| Scope owner | Condition | State |
| --- | --- | --- |
| Any included season | Required complete observation absent | `RefreshSeason(reason="missing")` |
| Historical season | Complete | Continue without refresh |
| Non-latest primary | Complete | Continue without refresh |
| Latest primary, readiness-only | Complete | Continue without refresh |
| Latest primary, live | Complete and fresh | Continue without refresh |
| Latest primary, live | Complete but too old | `RefreshSeason(reason="stale")` |
| Later season | Exact roster mapping absent | `MapSeasonRosters` |

The live age maximum is configured by
`AIDAM_GENERATION_REFRESH_MAX_AGE_SECONDS`, default `900`. An injected clock
owns comparison. Freshness is the minimum completion time across the latest
primary season's selected requirements, so one old required scope makes the
season stale.

The player catalog is readiness-only and does not make every live preparation
stale. Historical seasons never age-refresh automatically. An operator may use
manual refresh when completed history needs correction.

## Refresh Execution

Automatic refresh uses a deterministic durable active key scoped to the season,
cutoff, policy version, reason, and pre-refresh coverage fingerprint. A partial
unique constraint allows one active equivalent automatic refresh. The winner
delegates to the standard one-season refresh; other callers join with a bounded
wait. Stale active claims follow one recovery path owned entirely by the
coordinator.

The standard refresh remains full rather than accepting a generated endpoint
plan. This keeps API dependencies, normalization order, and partial failure
semantics in the existing refresh module. It may refetch the player catalog or
NFL state. Endpoint TTLs and partial refresh execution are intentionally out of
scope until traffic and latency measurements show a need.

Refresh completion is not proof that inputs are ready. Whether the run succeeded,
partially completed, failed, or was joined, the preparation facade re-runs the
resolver. This single rule defines partial-run and concurrent-write behavior.

## Roster Mapping

The oldest season may use the existing safe franchise bootstrap. Later seasons
require explicit roster-to-franchise mappings. The resolver compares roster IDs
from the selected raw roster payload with immutable core mappings. It never
matches on team name, manager name, array position, or reused Sleeper roster ID
across seasons.

A mapping correction participates in `input_revision`, so an earlier artifact
cannot be reused with a changed franchise interpretation.

## Frozen Revision and Build Handoff

Once ready, the resolver freezes:

- ordered season identities, settings, roles, and cutoffs;
- exact selected request and payload identifiers/hashes;
- exact season-roster/franchise mappings;
- the canonical `input_revision` over all output-affecting values.

Only this object crosses into snapshot construction. Build claim happens after
the freeze, and the builder resolves only the referenced immutable records. It
does not query for “latest,” recompute mappings, or restart selection. A refresh
or mapping change that commits later belongs to the next preparation call.

## Failure Semantics

- Required mapping: stop with `RosterIdentityMappingRequired` and keep fetched
  evidence for mapping/retry.
- Claim/join/refresh failure: `RefreshUnavailable` identifies season and run.
- Joined wait timeout: retryable `RefreshUnavailable`.
- Same season still missing/stale after its one attempt:
  `SnapshotInputsUnavailable` with exact recomputed scopes.
- Contradictory lineage, scope ownership, payload identity, or mapping:
  `DatalayerScopeConflict`.
- Cancellation: stop before another action; completed refresh audit remains and
  no snapshot is claimed from unresolved inputs.

There is no manifest-change retry, ambiguous skip action, or success-with-
warnings snapshot state.

## Observability

Record mode, policy version, maximum age, each returned state, affected season,
reason, missing scopes, candidate ages, claimed/joined refresh IDs, wait time,
re-resolution result, final `input_revision`, and snapshot ID. Generation
manifests retain refresh receipts plus ordered included-season coverage.

Measure refresh count, coalescing rate, preparation latency, artifact build
latency, artifact bytes, and season count before adding policy complexity.
