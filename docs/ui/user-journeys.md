# UI User Journeys and Page Model

## User and Mental Model

The initial user is the league reporter/operator. They understand seasons,
weeks, Sleeper league IDs, and article prompts, but should not need to understand
database revisions, artifact foreign keys, or snapshot build keys to complete a
normal task.

The application answers four questions in order:

1. Which competition am I working in?
2. Is its selected season's data fresh enough?
3. What should the reporter generate, against which historical boundary and
   model chain?
4. What did it produce, how did it get there, and what did it consume?

## Information Architecture

```text
Competitions
├── Competition overview
│   ├── Seasons and Sleeper IDs
│   ├── Refresh actions and freshness
│   └── Recent activity
├── Articles
│   ├── Article history
│   └── Generation detail
│       ├── Article
│       ├── Artifacts
│       ├── Execution
│       └── Usage
└── Generate
    ├── Live generation
    └── Historical backtest
        └── Review and promote/discard evaluation memory
```

A persistent application shell contains the product name, a competition
switcher, and primary competition navigation. Breadcrumbs carry the selected
competition and current resource. A narrow viewport collapses navigation into
a sheet, but tables retain meaningful card/list alternatives instead of
requiring horizontal scrolling for core actions.

## Route and Page Inventory

| Route                                                    | Page                 | Primary responsibility                                       |
| -------------------------------------------------------- | -------------------- | ------------------------------------------------------------ |
| `/`                                                      | Redirect             | Continue to `/competitions` or the last valid competition    |
| `/competitions`                                          | Competition list     | Browse, create, archive, and choose a competition            |
| `/competitions/:competitionId`                           | Competition overview | Seasons, freshness, refresh history, and recent runs         |
| `/competitions/:competitionId/articles`                  | Article history      | Filter and browse submitted articles for one competition     |
| `/competitions/:competitionId/generate`                  | Generate article     | Configure, validate, and submit a generation                 |
| `/competitions/:competitionId/generations/:generationId` | Generation detail    | Article/run status plus artifacts, execution, and usage tabs |

Creation stays in a dialog or sheet on `/competitions`; it does not need a
dedicated route in v1. Season creation is a dialog on the competition overview.
The generation detail route represents pending, running, failed, cancelled, and
successful runs. Successful article-history entries link to the same route,
avoiding a second detail model for “article” versus “generation.”

## Journey 1: View and Manage Leagues

### Competition list

The list shows display name, season count, latest season, last successful
Sleeper refresh, most recent article, and an attention state. Empty state copy
explains that a competition is the cross-season identity and offers `Create
competition`.

Creating a competition asks only for a display name. After success, the user is
taken to its overview and prompted to add a season.

### Add a season

The add-season dialog asks for:

- season year;
- Sleeper league ID; and
- sequence/order only if it cannot be derived from existing seasons.

Before saving, the UI explains that Sleeper creates a new league ID for each
season. Duplicate season years and globally reused Sleeper league IDs are
reported inline from typed API conflicts. The UI does not guess that linked
Sleeper predecessor/successor IDs belong to the same AIdam competition.

The first refresh of the competition's first season creates one durable team
identity per observed roster. For a later season, a complete roster observation
may pause normalization until the operator maps every Sleeper roster to one
unused existing team or creates a new team. The setup view shows team and owner
labels only as evidence; it never preselects cross-season continuity. After the
mapping is saved, the application starts a fresh full refresh using the prior
requested through-week value.

### Competition overview

The page header shows competition name and the active/latest season selector.
Each season row/card shows:

- year and Sleeper league ID;
- normalized Sleeper league name and status when data exists;
- latest refresh outcome and completion time;
- requested through-week boundary;
- request success/failure counts; and
- latest ready generation snapshot time, if one exists.

`Refresh Sleeper data` opens a confirmation sheet with the selected season and
an optional through-week field. Blank means the backend derives the effective
week from NFL state. While the synchronous request is in flight, the button is
disabled and progress copy makes clear that multiple Sleeper endpoints are
being fetched. Success, partial success, and failure are distinct outcomes.
A partial refresh remains inspectable and never claims the season is fully
fresh.

Refresh history is a compact table with status, trigger, requested through
week, started/completed times, and request counts. A row can expand to endpoint
scope results once the audit API supplies them.

### Freshness rules

- “Last refreshed” uses the latest terminal refresh completion time.
- “Last successful refresh” excludes partial and failed outcomes.
- A running refresh is shown separately and never overwrites the last successful
  timestamp.
- Snapshot time is not used as Sleeper freshness. It tells the user when a
  frozen generation input was built/reused.
- Timestamps show relative time with exact local time in a tooltip or detail.

## Journey 2: Generate an Article

### Form layout

The page uses a two-column layout on wide screens: the form on the left and a
sticky run summary on the right. Sections are:

1. **Scope:** season, start week, end week, and generation mode.
2. **Assignment:** plain-language request text, focus teams/topics, and topics
   to avoid.
3. **Voice:** voice, target length, evidence policy, profanity policy, tone
   controls, and optional team bias framing.
4. **Models:** primary model and ordered unique fallback models.
5. **Advanced execution:** retry and maximum-turn controls, collapsed by
   default.

The primary button is `Generate article`. Defaults come from a backend model
catalog and frontend form defaults, not from a previous run unless the user
explicitly chooses `Use these settings` on that run.

### Generation modes

The initial form presents the backend's two supported product modes:

| Mode                | Factual boundary       | Memory effect                                | Promotion                                    |
| ------------------- | ---------------------- | -------------------------------------------- | -------------------------------------------- |
| Live                | Selected week boundary | Writes canonical memory on success           | Not applicable; already canonical            |
| Historical backtest | Historical week cutoff | Historical pinned memory, isolated/read-only | Not eligible under the accepted architecture |

Live mode is described as “generate from the selected week boundary and current
canonical reporter memory.” It is available for every attached season, including
completed seasons, but does not rewind canonical memory. The form advises users
to start from empty memory and run chronologically when rebuilding a season. The
page shows the last successful refresh and warns when no usable observations
exist. Because generation currently never refreshes implicitly, the warning
provides a `Refresh now` action and returns to the preserved form afterward.

### Backtest behavior

Backtest mode makes the historical boundary prominent and explains that future
Sleeper data is physically excluded from the frozen snapshot. It also explains
the memory limitation accurately: the backtest path pins an earlier canonical
revision and disables writes.

The initial product does not expose current simulation, writable backtest,
workspace, promotion, discard, merge, rebase, or stale-workspace recovery
controls. Those behaviors require a separate memory-architecture decision and
must not be inferred from unused database scaffolding.

### Model selection

The primary model is a combobox sourced from the backend catalog. Fallbacks are
an ordered list with add, remove, and reorder controls. The primary model cannot
also appear as a fallback, and fallbacks cannot repeat. Each option shows
provider, model label/ID, default status, and reasoning support. The catalog is
selection metadata only; the frontend never receives token rates or calculates
cost.

### Submission and progress

On `201 Created`, navigate to the generation detail page. Pending/running views
show status, stage, turn, elapsed time, model chain, scope, and request. Polling
continues while the tab is visible and stops at a terminal status. Reloading the
page resumes from durable backend state. Failure keeps the request/settings
visible and offers `Rerun` plus `Edit settings and try again`.

## Journey 3: View Articles and Audit Runs

### Article history

Article history is competition-scoped and newest-first. Filters include season,
live/backtest kind, week or week range, model, and a free-text request search
when the API supports it. Each row/card shows:

- completion time;
- season and week range;
- live/backtest badge;
- request excerpt;
- requested primary model;
- token total and estimated cost when available; and
- rerun/workspace relationship.

Only generations with an explicit submitted artifact version appear here.
Pending and failed work remains on recent activity/run history, not in the
article library.

### Generation detail tabs

**Article** renders the exact submitted Markdown version with readable editorial
typography. A metadata rail shows request, dates, mode, model chain, snapshot,
memory input, and manifest hash. `Copy Markdown` is available; editing and
publishing are deferred.

**Artifacts** lists logical path, media type, finalization state, revision
count, and modified time. Selecting an artifact shows its version history and
content. The submitted version is visibly marked. Arbitrary HTML in artifacts
is not executed.

**Execution** presents a chronological turn timeline. AI attempts show
requested/actual model, status, latency, finish reason, and usage. Nested tool
calls show tool name, status, duration, arguments, structured result/full text,
and errors in expandable panels. Large JSON/text starts collapsed, is copyable,
and is never loaded into the article reading surface by default.

**Usage** shows aggregate input, cached input, output, reasoning, and total
tokens; model/provider breakdown; attempt count; latency; and estimated cost.
The quote time and “estimated” label are always visible. Unknown price or usage
produces an incomplete-estimate warning and identifies the affected calls.

## Common States and Guardrails

Every page defines loading skeleton, empty, permission/not-found, recoverable
error, and stale-data states. Mutations use inline errors plus a toast for the
outcome; toasts never contain the only explanation of a failure.

Destructive or canonical-state operations require confirmation. Ordinary
creation, refresh, generation, and rerun actions do not require a second generic
confirmation unless they have an unusual consequence.

All controls are keyboard reachable, status is conveyed by text as well as
color, focus returns predictably after dialogs, data tables have accessible
headers, and polling status updates use a non-disruptive live region.
