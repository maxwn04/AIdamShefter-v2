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

| Capability | Route | UI readiness |
| --- | --- | --- |
| Submit generation | `POST /generations/competitions/{competition_id}` | Implemented; body already includes kind, season, weeks, primary model, and nested settings |
| Rerun exact request | `POST /generations/competitions/{competition_id}/{generation_id}/reruns` | Implemented |
| Run history | `GET /generations/competitions/{competition_id}` | Implemented with season/kind/status/rerun filters |
| Submitted article history | `GET /generations/competitions/{competition_id}/articles` | Implemented with season/kind filters |
| Run detail | `GET /generations/competitions/{competition_id}/{generation_id}` | Implemented |
| Submitted article | `GET /generations/competitions/{competition_id}/{generation_id}/article` | Implemented and returns the exact generation, artifact, and version |
| AI call list/detail | `GET .../{generation_id}/ai-calls[/{ai_call_id}]` | Implemented |
| Tool call list/detail | `GET .../{generation_id}/tool-calls[/{tool_call_id}]` | Implemented |
| Artifact list/detail | `GET .../{generation_id}/artifacts[/{artifact_id}]` | Implemented |
| Artifact versions | `GET .../{generation_id}/artifacts/{artifact_id}/versions[/{version_id}]` | Implemented |

The current `backend/api/routes/data.py` registers only an empty `/data`
router. Core competition/season persistence, refresh service, snapshot manager,
and evaluation-workspace tables exist, but they do not yet have complete
product resource/service/HTTP surfaces.

The existing generation route hierarchy is functional but inverted. Before a
public client contract is stable, consider moving it to
`/api/v1/competitions/{competition_id}/generations/...` alongside the new
competition resources. If it remains unchanged, the frontend API adapter must
hide that path irregularity from feature code.

## Required Competition API

Recommended routes:

| Method and path | Purpose | Status |
| --- | --- | --- |
| `GET /competitions` | List active competitions with season/freshness/article summary | Missing |
| `POST /competitions` | Create `{display_name}` | Missing |
| `GET /competitions/{competition_id}` | Competition detail and summary | Missing |
| `PATCH /competitions/{competition_id}` | Rename or archive through explicit allowed fields | Missing |
| `GET /competitions/{competition_id}/seasons` | Ordered season list | Missing |
| `POST /competitions/{competition_id}/seasons` | Attach `{season_year, sleeper_league_id}` and derive sequence | Missing |
| `GET /competitions/{competition_id}/seasons/{season_id}` | Season identity plus normalized league overview when present | Missing |

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

The list/detail projection should include summaries the UI otherwise has to
assemble with N+1 requests: season count/latest season, latest terminal and
successful refresh timestamps, latest ready snapshot time, and latest submitted
article time. These are read projections, not denormalized write contracts.

Season creation must return `409` codes for at least
`competition_season_year_exists` and `sleeper_league_id_exists`. Editing an ID
after observations exist is out of v1 scope; the API should not expose a broad
season patch until that lifecycle is designed.

## Required Refresh and Data Audit API

| Method and path | Purpose | Status |
| --- | --- | --- |
| `POST /data/competitions/{competition_id}/seasons/{season_id}/refreshes` | Run manual refresh with optional `{through_week}` | Service exists; route missing |
| `GET /data/competitions/{competition_id}/seasons/{season_id}/refreshes` | Page refresh history | Manager list/query missing |
| `GET /data/competitions/{competition_id}/seasons/{season_id}/refreshes/{refresh_id}` | Read terminal/running refresh and counts | Manager get exists; route missing |
| `GET /data/competitions/{competition_id}/seasons/{season_id}/overview` | Normalized league metadata/current overview | Manager read exists; route missing |
| `GET /data/competitions/{competition_id}/seasons/{season_id}/snapshots` | Page snapshot audit metadata | Snapshot resource exists; list route/query missing |

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

## Generation API Extensions

The existing generation contract is enough to create basic live and read-only
backtest runs. These additions complete the planned UI:

| Method and path | Purpose | Priority |
| --- | --- | --- |
| `POST .../{generation_id}/cancel` | Cancel a pending/running generation | Should-have; manager supports cancellation |
| Extend article/run list query | Model, week overlap, completion range, request text | Later unless list size demands it |
| Extend generation body | Explicit memory mode and optional `evaluation_workspace_id` for isolated simulation sequencing | Required for workspace promotion |
| `GET .../{generation_id}/usage` | Aggregate tokens, latency, calls, and price quote | Required |
| Optional `GET .../{generation_id}/audit` | One bounded detail projection for article + artifacts + calls | Optimization only; existing resources remain authoritative |

The UI polls run detail. WebSockets or server-sent events are not required for
v1. A future event channel must remain an acceleration layer; durable GET state
is still the recovery authority.

## Model Catalog and Pricing

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
  "selectable": true,
  "is_default": false,
  "supports_reasoning": true,
  "pricing_revision": "2026-08-23",
  "pricing": {
    "currency": "USD",
    "input_per_million": "0.000000",
    "cached_input_per_million": "0.000000",
    "output_per_million": "0.000000"
  }
}
```

Prices above are shape examples, not values. Decimal strings avoid binary float
rounding in the transport. The backend configuration/service owns model aliases,
availability, provider billing semantics, and pricing revisions.

`GET .../{generation_id}/usage` aggregates **all recorded attempts**, including
failed/fallback attempts when the provider reported billable usage. It prices
the actual provider/model, not merely the requested primary model. A response
contains:

- totals by token class;
- breakdown by actual provider/model;
- unpriced/missing-usage call IDs;
- pricing revision(s) and quote time;
- estimated cost as a decimal string and currency; and
- `complete: false` whenever any applicable call cannot be priced.

Cached tokens must not be double-counted as full-price input when provider usage
reports them as a subset. Reasoning-token billing differs by provider/model and
must be captured in the pricing rule rather than guessed by the frontend. The
first implementation may keep the pricing catalog in versioned server
configuration. Persisted historical dollar cost is not required; persisted raw
usage plus a reproducible price revision is.

## Evaluation Workspace and Promotion API

The database schema anticipates workspaces, but a public manager/service/API is
missing. Promotable current simulations and longitudinal evaluations require:

| Method and path | Purpose |
| --- | --- |
| `POST /competitions/{competition_id}/evaluation-workspaces` | Create an active workspace pinned to a server-selected canonical base revision |
| `GET /competitions/{competition_id}/evaluation-workspaces/{workspace_id}` | Status, base/current artifact, generations, and promotion eligibility |
| `POST /competitions/{competition_id}/evaluation-workspaces/{workspace_id}/promote` | Fast-forward isolated memory into one new canonical revision |
| `POST /competitions/{competition_id}/evaluation-workspaces/{workspace_id}/discard` | Close without canonical mutation |

Workspace creation accepts the competition season/use case but does not accept
an arbitrary untrusted canonical base from the browser; the service resolves and
returns it. Generation submission accepts the resulting workspace ID only for
an isolated memory mode. The service allocates sequence numbers and pins the
workspace's current memory artifact.

Promotion is an atomic command with an expected workspace/current-artifact
version. It succeeds only when the workspace is active, its final memory
artifact is complete, and the canonical head still equals its base revision.
Otherwise it returns a typed `409 workspace_base_stale` or lifecycle conflict.
No automatic merge or partial promotion is allowed. Consequently, a current
simulation may be promotable and a historical old-base backtest is
evaluation-only.

Until these contracts exist, the UI must accurately offer basic read-only
backtests and hide promotion rather than exposing a control that cannot preserve
simulated memory.

## Article List Projection Gap

The implemented article list returns `GenerationSummary`, which has no article
title/excerpt, actual-model summary, aggregate tokens, cost, or log counts. A
first UI can fetch these after opening one article, but a useful paged library
must not issue child requests for every row. Extend the article summary read
model with submitted-output presentation metadata and usage summary, or add a
dedicated article projection. Title should eventually be persisted as output
metadata; deriving the first Markdown heading is only an MVP fallback.

## Error and Pagination Contract

New routes should converge on:

```json
{
  "error": {
    "code": "stable_machine_code",
    "summary": "Safe operator-facing summary",
    "field_errors": {"sleeper_league_id": ["Already attached"]},
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
