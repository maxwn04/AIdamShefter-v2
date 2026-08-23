# Product UI Design

**Status:** Proposed product and frontend contract

**Scope:** Competition management, article generation, generated-article
inspection, execution audit, and usage/cost visibility

**Backend baseline:** The modular monolith under `backend/`

## Purpose

This design turns the backend platform into an operator-facing application for
running one or more fantasy-football reporters. It starts with three complete
journeys:

1. create a durable competition, attach its Sleeper league ID for each season,
   refresh source data, and understand data freshness;
2. configure and start a live generation or historical backtest, including the
   primary and fallback model chain; and
3. browse submitted articles by competition and inspect the exact generation,
   artifacts, model/tool execution, token usage, and estimated cost behind each
   article.

The first release is a local single-operator product. Authentication, hosted
multi-user ownership, collaborative editing, and public article publishing are
not part of this UI slice.

## Documents

| Document | Owns |
| --- | --- |
| [`user-journeys.md`](user-journeys.md) | Information architecture, page inventory, flows, and user-visible states |
| [`application-contracts.md`](application-contracts.md) | Required HTTP surface, implemented coverage, gaps, and transport semantics |
| [`frontend-architecture.md`](frontend-architecture.md) | TypeScript application structure, libraries, data flow, quality gates, and delivery |

The dependency-ordered implementation plan is intentionally local and mutable
under `.context/ui/stack.md`, following the existing datalayer, memory, and
generation workflow.

## Product Vocabulary

The UI must use the backend's domain words consistently:

| Term | Product meaning |
| --- | --- |
| Competition | A continuous fantasy league identity across multiple seasons |
| Season | One competition year mapped to exactly one Sleeper league ID |
| Refresh | A manual pull from Sleeper that records source observations and updates the normalized current view |
| Snapshot | An immutable, cutoff-safe SQLite generation input built or reused by the generation service |
| Generation / run | One durable reporter execution, whether or not it succeeds or submits an article |
| Article | The exact submitted artifact version of a successful generation |
| Artifact | A versioned Markdown work product created during a generation |
| Live generation | A run using the requested current-season boundary and canonical memory |
| Backtest | A historical, cutoff-aware run isolated from canonical memory writes |
| Evaluation workspace | Isolated simulated memory state that may be explicitly discarded or fast-forward promoted |

In particular, the league screen says **Refresh Sleeper data**, not “create a
snapshot.” A refresh calls Sleeper; a snapshot is a separate reproducibility
artifact created for a generation. The screen can show both timestamps, but it
must not collapse them into one freshness concept.

User-facing navigation may say **Leagues** because that is the familiar fantasy
football term. Routes, API contracts, and code retain `competition` for the
durable cross-season identity.

## Settled Product Decisions

- The application opens on the league/competition list. After a competition is
  selected, primary navigation is `Overview`, `Articles`, and `Generate`.
- A competition may be created before any season exists. It is not ready to
  refresh or generate until at least one season is attached.
- A season's Sleeper league ID is treated as durable identity once source data
  or generations reference it. Correction is a backend lifecycle operation,
  not an unrestricted text-field edit in the first UI.
- Manual refresh is explicit. Starting a generation does not silently refresh
  Sleeper data; the form shows freshness and lets the operator refresh first.
- Generation submission navigates immediately to the durable run page. The UI
  polls that page until the run is terminal and survives browser reloads.
- Advanced reporter controls are available but visually secondary to season,
  week range, mode, request, and model chain.
- Generation intent has two dimensions: current versus historical factual time,
  and canonical versus isolated memory effects. Current canonical work is a
  live generation; current isolated work is a simulation that may be
  fast-forward promoted; historical work is a backtest and is evaluation-only
  under the accepted memory contract.
- Isolated memory never changes canonical memory merely because a run
  succeeded. Promotion is a separate, confirmed command available only when
  the workspace started from the still-current canonical revision.
- Article content is rendered from the exact submitted artifact version.
  Intermediate artifacts and later/earlier versions never replace it by path
  convention.
- Cost is labeled **estimated cost**. The backend calculates it from persisted
  actual provider/model usage and a named pricing revision; missing usage or
  pricing remains visibly unknown rather than being treated as zero.
- The package manager is `pnpm`. Yarn and npm lockfiles are not introduced.

## Release Boundary

The first useful release includes:

- competition and season CRUD needed by the three journeys;
- synchronous manual refresh plus refresh history/freshness reads;
- model catalog and generation form;
- polling-oriented run state;
- article history and article/run detail;
- artifacts, AI calls, tool calls, aggregate token usage, and cost estimate; and
- isolated one-workspace-at-a-time current simulation and fast-forward
  promotion if the backend workspace service lands in the same release.

Memory browsing/editing, comparisons, scheduled generation, templates, public
publishing, dashboards across competitions, and streaming execution logs are
deliberately deferred.

The requested ability to promote memory from a historical backtest conflicts
with the accepted backend invariant that an old-base workspace is
evaluation-only. Supporting that behavior would require an explicit memory
architecture change (merge/rebase or a different meaning of “backtest”), not
just a UI control. The safe initial product promotes current-based simulations
and keeps historical backtests isolated.
