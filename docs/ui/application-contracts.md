# UI Application and API Contracts

## Contract Principles

- The frontend consumes only `/api/v1` HTTP contracts. It never imports Python
  domain objects or depends on database schemas.
- Competition scope remains explicit in URLs and must agree with returned
  resource scope.
- Writes are domain commands, not generic table patches.
- List responses use `{items, total, limit, offset}` semantics consistently.
- Timestamps are timezone-aware ISO 8601 values; the frontend localizes them.
- IDs remain opaque UUID strings. Sleeper league IDs remain strings.
- API errors need a stable machine code, safe summary, and optional field
  details so forms do not parse exception text.
- The generated OpenAPI document is the source for TypeScript transport types.

## Current Backend Coverage

Generation routes already exist under
`/api/v1/generations/competitions/{competition_id}`:

| Capability                | Route                                                                     | UI readiness                                                                                                                                              |
| ------------------------- | ------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Submit generation         | `POST /generations/competitions/{competition_id}`                         | Implemented; body includes kind, season, explicit weeks, primary model, and nested settings, and rejects a primary model duplicated in the fallback chain |
| Rerun exact request       | `POST /generations/competitions/{competition_id}/{generation_id}/reruns`  | Implemented                                                                                                                                               |
| Run history               | `GET /generations/competitions/{competition_id}`                          | Implemented with season/kind/status/rerun filters                                                                                                         |
| Submitted article history | `GET /generations/competitions/{competition_id}/articles`                 | Implemented with season/kind filters and a set-based article/usage projection                                                                             |
| Run detail                | `GET /generations/competitions/{competition_id}/{generation_id}`          | Implemented                                                                                                                                               |
| Submitted article         | `GET /generations/competitions/{competition_id}/{generation_id}/article`  | Implemented and returns the exact generation, artifact, and version                                                                                       |
| AI call list/detail       | `GET .../{generation_id}/ai-calls[/{ai_call_id}]`                         | Implemented                                                                                                                                               |
| Tool call list/detail     | `GET .../{generation_id}/tool-calls[/{tool_call_id}]`                     | Implemented                                                                                                                                               |
| Artifact list/detail      | `GET .../{generation_id}/artifacts[/{artifact_id}]`                       | Implemented; list summaries include revision count and latest-version time                                                                                |
| Artifact versions         | `GET .../{generation_id}/artifacts/{artifact_id}/versions[/{version_id}]` | Implemented                                                                                                                                               |

Competition and season management plus refresh, overview, and snapshot-audit
routes are implemented. Evaluation-workspace tables exist, but writable
simulations and their product/API surfaces are explicitly deferred beyond the
initial release pending a new memory-architecture decision.

The existing generation route hierarchy is functional but inverted. Before a
public client contract is stable, consider moving it to
`/api/v1/competitions/{competition_id}/generations/...` alongside the new
competition resources. If it remains unchanged, the frontend API adapter must
hide that path irregularity from feature code.

## Required Competition API

Recommended routes:

| Method and path                                                          | Purpose                                                              | Status      |
| ------------------------------------------------------------------------ | -------------------------------------------------------------------- | ----------- |
| `GET /competitions`                                                      | List active competitions with season/freshness/article summary       | Implemented |
| `POST /competitions`                                                     | Create `{display_name}`                                              | Implemented |
| `GET /competitions/{competition_id}`                                     | Competition detail and summary                                       | Implemented |
| `PATCH /competitions/{competition_id}`                                   | Rename or archive through explicit allowed fields                    | Implemented |
| `GET /competitions/{competition_id}/seasons`                             | Ordered season list                                                  | Implemented |
| `POST /competitions/{competition_id}/seasons`                            | Attach `{season_year, sleeper_league_id}` and derive sequence        | Implemented |
| `GET /competitions/{competition_id}/seasons/{season_id}`                 | Season identity plus normalized league overview when present         | Implemented |
| `GET /competitions/{competition_id}/seasons/{season_id}/roster-mappings` | Read roster-identity readiness and observed mapping evidence         | Implemented |
| `PUT /competitions/{competition_id}/seasons/{season_id}/roster-mappings` | Atomically map every observed roster to an existing or new franchise | Implemented |

Example creation response:

```json
{
  "competition": {
    "id": "uuid",
    "display_name": "The League",
    "created_at": "2026-08-23T12:00:00Z",
    "updated_at": "2026-08-23T12:00:00Z",
    "archived_at": null
  }
}
```

`PATCH /competitions/{competition_id}` accepts exactly one sparse change:

```json
{ "display_name": "Renamed League" }
```

or:

```json
{ "archived": true }
```

Empty bodies, null values, `archived: false`, combined changes, and unknown
fields are rejected with `422`. Restore remains out of scope.

The list/detail projection should include summaries the UI otherwise has to
assemble with N+1 requests: season count/latest season, latest terminal and
successful refresh timestamps, latest ready snapshot time, and latest submitted
article time. These are read projections, not denormalized write contracts.

Competition list items and detail responses carry the canonical competition
beside that activity summary. Season list items carry the canonical season,
normalized league name/status when available, latest terminal refresh status,
boundary and counts, latest successful refresh time, and latest ready snapshot
time. Season detail adds the complete normalized league overview when one has
been loaded; before the first refresh that field is `null`.

Typed competition errors use the new product envelope:

```json
{
  "error": {
    "code": "competition_season_year_exists",
    "summary": "that season year is already attached to this competition",
    "field_errors": { "season_year": ["Already attached to this competition."] }
  }
}
```

The stable core codes are `competition_not_found`,
`competition_season_not_found`, `competition_archived`,
`competition_season_year_exists`, `sleeper_league_id_exists`, and
`competition_concurrency_conflict`, `roster_mapping_conflict`, and
`roster_mapping_source_stale`.

Season creation must return `409` codes for at least
`competition_season_year_exists` and `sleeper_league_id_exists`. Editing an ID
after observations exist is out of v1 scope; the API should not expose a broad
season patch until that lifecycle is designed.

Competition archive is one-way in v1. Active competition lists exclude archived
rows by default, while direct competition and historical season reads remain
available. Repeating archive is idempotent; renaming an archived competition or
attaching another season is rejected. Restore and cascading changes to existing
generation or memory resources are out of scope.

The first complete roster observation for a competition's first season creates
one durable franchise per Sleeper roster because no cross-season identity choice
exists. Later seasons never infer continuity from team names, manager names, or
roster position. Their mapping resource reports `awaiting_source`,
`needs_mapping`, or `ready`; mutation requires the latest complete roster
request ID as an optimistic source token and exactly one target per observed
roster. Existing season-roster mappings are immutable.

## Required Refresh and Data Audit API

| Method and path                                                                      | Purpose                                           | Status      |
| ------------------------------------------------------------------------------------ | ------------------------------------------------- | ----------- |
| `POST /data/competitions/{competition_id}/seasons/{season_id}/refreshes`             | Run manual refresh with optional `{through_week}` | Implemented |
| `GET /data/competitions/{competition_id}/seasons/{season_id}/refreshes`              | Page refresh history                              | Implemented |
| `GET /data/competitions/{competition_id}/seasons/{season_id}/refreshes/{refresh_id}` | Read terminal/running refresh and counts          | Implemented |
| `GET /data/competitions/{competition_id}/seasons/{season_id}/overview`               | Normalized league metadata/current overview       | Implemented |
| `GET /data/competitions/{competition_id}/seasons/{season_id}/snapshots`              | Page snapshot audit metadata                      | Implemented |

V1 manual refresh may be synchronous because the implemented refresh service is
synchronous and the existing datalayer plan explicitly calls for a synchronous
manual route. It should return `201 Created` with a terminal `RefreshOutcome`.
The frontend must use a generous request timeout and show in-flight state. If
refresh duration becomes operationally unreliable, replace this with a durable
`202 Accepted` job boundary rather than pretending a background task is durable.

Request body:

```json
{
  "through_week": 8
}
```

Blank/null `through_week` asks the service to derive the effective week. The
server fixes the trigger to `manual`; callers do not claim trusted provenance.
The response includes the durable refresh, effective through week, and
scope-level results/warnings already represented by `RefreshOutcome`.

Refresh and snapshot history use offset pagination and deterministic newest-first
ordering. Snapshot audit responses expose immutable identity, cutoff, status,
versions, warnings/failure, and artifact hash/size, but never return local
filesystem paths or storage keys. The normalized overview returns `404` until a
league observation has been loaded for the season.

### Refresh-to-generation freshness gap

Snapshot identity currently uses season, cutoff week, UTC date, and projection
version; the first healthy ready snapshot for that daily key is reused. A
manual refresh later on the same day therefore does **not** guarantee that the
next generation sees the newly recorded observations if a matching ready
snapshot already exists.

That behavior is consistent with the present datalayer contract but conflicts
with the natural product expectation “refresh, then generate from the refresh.”
Before calling the journey complete, the datalayer design must choose one of:

- make selected source-head identity part of snapshot identity;
- let snapshot resolution require observations at least as new as a specific
  refresh run and create a new immutable revision when needed; or
- state clearly that refresh does not invalidate the daily generation snapshot
  and offer a separate explicit rebuild policy.

The UI cannot solve this with cache invalidation. It needs a backend snapshot
selection guarantee and corresponding audit metadata.

This redesign is explicitly deferred from the refresh/data-audit HTTP layer to a
later datalayer-owned change. Until then, the daily snapshot reuse behavior
described above remains authoritative.

## Generation API Extensions

The existing generation contract is enough to create basic live and read-only
backtest runs. These additions complete the planned UI:

For Layer 7, the UI always submits explicit `week_start` and `week_end` values;
it does not derive or imply a current week. Live mode is available for any
attached season and selected week boundary. A live run pins the current
canonical memory head and may append a new revision on success; it does not
rewind memory to the selected season or week. Rebuilding a completed season
cleanly therefore requires empty canonical memory and chronological live runs.
Backtest pins historical memory at or before the requested cutoff and cannot
write canonical memory.

The initial release does not expose an isolated or promotable simulation mode.
Evaluation-workspace and promote/discard contracts are deferred; the available
historical backtest is read-only.

| Method and path                          | Purpose                                                       | Priority                                                   |
| ---------------------------------------- | ------------------------------------------------------------- | ---------------------------------------------------------- |
| `POST .../{generation_id}/cancel`        | Cancel a pending/running generation                           | Should-have; manager supports cancellation                 |
| Extend article/run list query            | Model, week overlap, completion range, request text           | Later unless list size demands it                          |
| Extend generation body                   | Explicit writable draft-memory mode                           | Deferred pending memory architecture decision              |
| `GET .../{generation_id}/usage`          | Aggregate tokens, latency, calls, and price quote             | Required                                                   |
| Optional `GET .../{generation_id}/audit` | One bounded detail projection for article + artifacts + calls | Optimization only; existing resources remain authoritative |

The UI polls run detail. WebSockets or server-sent events are not required for
v1. A future event channel must remain an acceleration layer; durable GET state
is still the recovery authority.

## Model Catalog and Backend Pricing

The form must not hard-code the deployable model set. Add:

```text
GET /api/v1/models
```

Each item includes:

```json
{
  "provider": "openai",
  "model": "model-id",
  "display_name": "Display name",
  "is_default": false,
  "supports_reasoning": true
}
```

The list is the ordered, deduplicated `REPORTER_MODEL` and
`REPORTER_FALLBACK_MODELS` chain. It is selection metadata only: the frontend
does not receive token rates and generation submission remains permissive.

`GET .../{generation_id}/usage` aggregates **all recorded attempts**, including
failed/fallback attempts when the provider reported billable usage. It prices
the actual provider/model, not merely the requested primary model. A response
contains:

- totals by token class;
- breakdown by actual provider/model;
- unpriced/missing-usage call IDs;
- quote time;
- estimated cost as a decimal string and currency; and
- `complete: false` whenever any applicable call cannot be priced.

Cached tokens must not be double-counted as full-price input when provider usage
reports them as a subset. Reasoning-token billing differs by provider/model and
must be captured in the pricing rule rather than guessed by the frontend. The
backend uses the current LiteLLM price map and may fall back to the map bundled
with the installed LiteLLM package when the remote map is unavailable.
Historical price reproduction and persisted dollar cost are not required.

## Deferred Writable Simulation and Promotion

The initial release intentionally adds no evaluation-workspace manager,
service, route, or UI. Existing database seams remain unused and must not be
treated as an accepted serialized-artifact architecture.

Before adding writable simulations, compare revision-native draft lineages
against serialized reporting-owned workspace artifacts. The preferred option to
evaluate lets live generations advance canonical memory, backtests advance an
isolated draft lineage, and promotion publish only a draft whose base remains
the canonical head. This requires adapting or replacing the current linear
introduced/retired visibility model, which is not branch-safe.

The following route shapes are historical design candidates, not committed
initial-release contracts:

| Method and path                                                                    | Purpose                                                                        |
| ---------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| `POST /competitions/{competition_id}/evaluation-workspaces`                        | Create an active workspace pinned to a server-selected canonical base revision |
| `GET /competitions/{competition_id}/evaluation-workspaces/{workspace_id}`          | Status, base/current artifact, generations, and promotion eligibility          |
| `POST /competitions/{competition_id}/evaluation-workspaces/{workspace_id}/promote` | Fast-forward isolated memory into one new canonical revision                   |
| `POST /competitions/{competition_id}/evaluation-workspaces/{workspace_id}/discard` | Close without canonical mutation                                               |

Until a replacement architecture is accepted, the UI offers only live canonical
generation and read-only historical backtests and hides all workspace and
promotion controls.

## Article List Projection

The article list uses a dedicated set-based projection rather than returning a
plain `GenerationSummary` or issuing child requests for every row. It joins the
exact submitted artifact version and season presentation data, then reads the
page's compact AI usage in one additional query. Each summary includes article
identity, a first-H1-derived title with a deterministic fallback, assignment and
scope metadata, actual provider/model attempts, aggregate tokens, and the
backend-owned current-price estimate with completeness and quote time.

Title should eventually be persisted as explicit submitted-output metadata.
The derived Markdown heading is the accepted MVP presentation fallback and is
never used as durable identity.

## Error and Pagination Contract

New routes should converge on:

```json
{
  "error": {
    "code": "stable_machine_code",
    "summary": "Safe operator-facing summary",
    "field_errors": { "sleeper_league_id": ["Already attached"] },
    "correlation_id": "optional-id"
  }
}
```

Use `400` for malformed workflow input not covered by validation, `404` for
scope-masked absence, `409` for uniqueness/lifecycle/stale-base conflicts,
`422` for field validation, and `503` for unavailable external/runtime
dependencies. Refresh and generation failures that already created durable rows
should normally be read from those resources rather than erased into a generic
HTTP failure.

Offset pagination matches the implemented reporting managers and is sufficient
for v1. UI query keys must include competition, filters, limit, and offset.

Current reporting, memory, FastAPI validation, and readiness errors do not yet
share this shape. Until backend convergence lands, the frontend uses one API
error normalizer and components never branch on raw `detail` payload variants.
