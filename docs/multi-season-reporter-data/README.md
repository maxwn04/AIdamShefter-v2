# Multi-Season Reporter Data Design

**Status:** Implementation complete through operator integration; real-data
release gate pending

## Purpose

Give a reporter generation for one competition season reproducible, read-only
access to every earlier season in the same competition. Before freezing that
data, automatically plan and run only the season refreshes needed for complete,
fresh inputs. Historical facts remain inside the generation's immutable SQLite
snapshot; the model never queries live PostgreSQL and only pays tool/token cost
for history it chooses to inspect.

## Scope

This design covers season-lineage and refresh planning, generation-triggered
refresh coordination, historical input readiness, frozen snapshot selection and
materialization, the versioned SQLite schema, `FrozenLeagueData`, reporter tool
contracts, prompts, audit metadata, and the transition from single-season
snapshots.

It extends the app/backend path under `backend/services/datalayer/` and
`backend/services/reporter/`. The legacy `datalayer/` package remains a
single-season compatibility surface and is not the implementation target.

## Documents

| Document | Owns |
| --- | --- |
| [`architecture.md`](architecture.md) | Component boundaries, dependencies, lifecycle, and failure behavior |
| [`application-contracts.md`](application-contracts.md) | Public contracts, invariants, errors, and acceptance coverage |
| [`refresh-planning.md`](refresh-planning.md) | Readiness, freshness, refresh minimization, coordination, and input revision policy |

## Settled Direction

- A snapshot has one **primary season** and zero or more **historical seasons**.
- Historical scope is every competition season with a lower authoritative
  `sequence_number` than the primary season, ordered oldest to newest.
- The primary season is bounded by the generation's `through_week`; every
  historical season is materialized through week 18, including valid empty
  endpoint results after that league's final played week.
- Snapshot creation is complete-or-fail. Missing historical request scopes are
  reported just like missing primary-season scopes; the snapshot never silently
  omits an earlier season.
- Snapshot construction continues to replay sealed Sleeper observations. It does
  not fetch the Sleeper API or read normalized PostgreSQL heads as factual input.
- A small datalayer preparation facade runs before snapshot construction. A deep
  input resolver returns one typed next state at a time; refresh coordination
  executes only the oldest blocking season and then resolves again.
- Completed historical seasons are readiness-based, not age-refreshed. For an
  established competition, preparation therefore normally refreshes only the
  latest season—or skips refresh entirely when it is already fresh.
- A changed refresh or roster mapping must produce a new snapshot even on the
  same date. Snapshot identity includes a deterministic `input_revision` over
  season identity, selected scope/payload hashes, and exact mappings; identical
  facts continue to reuse the existing artifact.
- Existing curated tools continue to target the primary season by default. A
  caller may select an included season by year, and guarded SQL may query all
  included seasons.
- Durable `franchise_id` is the cross-season team identity. Sleeper `roster_id`,
  team name, manager name, and season-roster ID remain season-specific.
- A new snapshot projection/schema version is required. Existing ready snapshots
  remain readable under their old version but are never mutated.
- The primary season still owns generation and memory scope. Including historical
  facts does not change the generation's `competition_season_id`.
- The generation form reads the same network-free resolver state used by the
  API. Ready coverage is visible, refresh-required work may be prepared
  explicitly or left to generation, and exact historical mapping blockers link
  to that season's existing mapping workflow.

## Readiness and Cutover Gate

The code stack remains unmerged and undeployed until an operator reviews a
real-data readiness report. The gate is:

1. inspect every non-archived competition's latest attached season;
2. derive the cutoff from the newest successful refresh plan, classifying a
   missing usable cutoff as setup-required rather than guessing;
3. run readiness-only inspection and explicit preparation so fetchable
   historical gaps can backfill;
4. record the ready version-3 snapshot ID, factual revision, ordered coverage,
   refresh receipts, artifact size, and request duration;
5. record exact mapping blockers, resolve them through the normal mapping UI,
   and rerun readiness;
6. open at least one retained version-2 artifact when one exists;
7. stop for explicit approval before merge, migration application, deployment,
   cutover, or a live-generation smoke test.

## Non-Goals

- Direct reporter access to PostgreSQL or the Sleeper API.
- Cross-competition comparisons.
- Reconstructing facts from seasons that have not been attached, mapped, and
  refreshed into the competition.
- Manager/person identity history or franchise merge/split semantics.
- Changing reporter-memory scoping or copying historical facts into memory
  automatically.
- Silently guessing roster-to-franchise mappings for later seasons. Preparation
  stops with an actionable mapping requirement when setup is incomplete.
- Preserving the legacy `datalayer.SleeperLeagueData` public API as the app
  snapshot implementation.

## Open Questions

None block the proposed implementation. Product policy may later add an explicit
history depth limit, but `all previous seasons` is the initial contract and must
not be implemented as a silent best-effort subset.
