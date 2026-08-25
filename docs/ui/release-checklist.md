# UI Release Checklist

Use this checklist for the final comprehensive review of the local operator UI
against the real PostgreSQL database, FastAPI backend, Sleeper data, and model
provider. Run it after the complete initial UI stack is built, not after each
intermediate layer.

Writable simulations, evaluation workspaces, promotion, and discard are outside
this release. Do not enable or test those deferred flows here.

## Review Metadata

| Field                           | Value |
| ------------------------------- | ----- |
| Date and time                   |       |
| Reviewer                        |       |
| Commit                          |       |
| Branch                          |       |
| Operating system                |       |
| Browser and version             |       |
| Desktop viewport                |       |
| Mobile viewport or device       |       |
| Database identity/environment   |       |
| Competition and season reviewed |       |
| Sleeper league ID               |       |
| Primary and fallback models     |       |
| API base URL                    |       |
| Frontend URL                    |       |

Never paste database passwords, provider keys, full connection URLs, or private
model payloads into this record.

## Clean Bootstrap and Automated Gates

Start from a clean checkout with no existing frontend dependencies or running
application processes. The database may contain the full intended review data,
but the application must not depend on untracked code or stale generated files.

- [ ] Install the Python version pinned by the repository.
- [ ] Install Python dependencies from the locked dependency graph.
- [ ] Start the local PostgreSQL service and wait for its health check.
- [ ] Apply the complete Alembic history to head with the migrator role.
- [ ] Start FastAPI with the documented local environment.
- [ ] Confirm `/health/live` reports the process alive.
- [ ] Confirm `/health/ready` reports the database-backed service ready.
- [ ] Install the pinned pnpm version and use Node.js 22.22.x.
- [ ] Run `pnpm install --frozen-lockfile` in `frontend/`.
- [ ] Confirm the committed OpenAPI TypeScript contract has no drift.
- [ ] Confirm frontend formatting passes.
- [ ] Confirm frontend lint passes without warnings.
- [ ] Confirm strict TypeScript compilation passes.
- [ ] Confirm the production frontend build succeeds.
- [ ] Start the frontend through the documented local proxy configuration.
- [ ] Open the application through the documented frontend URL.

| Bootstrap or gate evidence  | Result  | Notes |
| --------------------------- | ------- | ----- |
| PostgreSQL and Alembic head | Pending |       |
| API liveness and readiness  | Pending |       |
| Frozen frontend install     | Pending |       |
| Generated API drift         | Pending |       |
| Format, lint, and typecheck | Pending |       |
| Production build            | Pending |       |

## Full Real-Database Journey

Use real persisted application rows and a real Sleeper refresh. Do not replace
the backend with a stub server. Capture generation IDs and concise notes where
they make a failure reproducible.

### Competition, Season, and Refresh

- [ ] The application opens on the competition list without console errors.
- [ ] The competition list handles its loading, empty, populated, and recoverable
      error states.
- [ ] Create or select the review competition.
- [ ] Create or select its season with the correct Sleeper league ID.
- [ ] Complete first-season roster identity onboarding, or confirm the existing
      durable identities are ready.
- [ ] If reconciliation is required, map every observed Sleeper roster to the
      intended franchise and retry safely after any stale-source response.
- [ ] Run **Refresh Sleeper data** against the real source.
- [ ] Confirm the refresh reaches its terminal state and history records the
      attempt, timestamps, scope, and any partial/rejected observations.
- [ ] If a refresh was interrupted by a hard process failure, first confirm no
      refresh process remains active, then run the bounded operator recovery:
      `uv run --env-file .env aidam-worker reconcile-stale-refreshes
    --competition-id <uuid> --stale-before <aware-ISO-timestamp> --limit 100`.
      Confirm the command reports the expected refresh IDs and statuses derived
      from durable attempts; it must not refetch or resume Sleeper work.
- [ ] Confirm the competition overview and generation form show consistent data
      freshness and readiness.
- [ ] Reload the page and confirm the persisted competition, season, identities,
      refresh history, and freshness remain correct.

### Live Generation

- [ ] Open **Generate** for the intended attached season and week boundary.
- [ ] Confirm live mode clearly describes canonical memory behavior.
- [ ] Select an explicit week or week range.
- [ ] Enter the assignment and review reporter voice, tone, bias, length, evidence,
      retry, turn-limit, primary-model, and ordered-fallback settings.
- [ ] Confirm the primary model cannot be duplicated in the fallback chain and
      fallbacks cannot repeat.
- [ ] Submit the generation and confirm navigation to its durable run page.
- [ ] Confirm pending/running status shows useful stage, turn, elapsed time,
      assignment, scope, and model-chain context.
- [ ] Reload while the run is active and confirm polling resumes from durable
      backend state.
- [ ] Move the browser to the background and restore it; confirm polling pauses and
      resumes appropriately without creating another generation.
- [ ] Confirm polling stops when the generation becomes terminal.
- [ ] If the run fails, confirm the failure is actionable and **Rerun** plus
      **Edit settings and try again** preserve the intended configuration.
- [ ] For the successful run, record the generation ID below.

Live generation ID: `____________________________`

### Historical Read-Only Backtest

- [ ] Select an older attached season or historical boundary and confirm the UI
      changes the run to backtest mode.
- [ ] Confirm the historical week cutoff and read-only memory behavior are explicit
      before submission.
- [ ] Confirm no current-simulation, workspace, promotion, discard, merge, or
      automatic-promotion control appears.
- [ ] Submit the backtest and confirm the durable status/reload/polling behavior
      matches the live run.
- [ ] Confirm a successful backtest produces an inspectable article without
      offering any canonical-memory promotion action.

Backtest generation ID: `____________________________`

### Article Library and Exact Article

- [ ] The article library contains only successful generations with an explicit
      submitted artifact version.
- [ ] Season and live/backtest filters produce the expected persisted rows.
- [ ] Each row presents its derived title, completion time, assignment excerpt,
      scope, requested/actual model summary, token total, and estimated cost when
      available.
- [ ] Open the live article and confirm the rendered Markdown is the exact submitted
      version identified by the generation, not a path-selected intermediate draft.
- [ ] Repeat the exact-version check for the backtest article.
- [ ] Confirm headings, lists, links, tables, code, and long lines remain readable
      and contained.
- [ ] Confirm raw HTML in Markdown does not execute.
- [ ] Confirm **Copy Markdown** copies the exact submitted content and provides
      visible feedback.
- [ ] Confirm article metadata matches the generation request, dates, mode, model
      chain, data snapshot, memory input, and manifest hash.

### Artifact and Version Audit

- [ ] The artifact list shows path, media type, finalization state, revision count,
      and modified time for the selected generation.
- [ ] Artifact and version pagination does not lose the active selection or alter
      the URL-backed tab state.
- [ ] Selecting an artifact loads its version history without eagerly loading every
      version body.
- [ ] Selecting a version loads that exact content and visibly marks submitted and
      finalized versions correctly.
- [ ] Markdown artifacts use the safe renderer; valid JSON is pretty-printed;
      textual HTML and other text appear only as escaped source.
- [ ] Unknown or binary media types do not execute in the browser.
- [ ] Copying artifact content copies the exact stored version rather than its
      presentation-only formatting.

### Execution Audit

- [ ] AI attempts appear in chronological turn/attempt order with requested and
      actual models, status, latency, finish reason, and token usage.
- [ ] AI-call pagination reaches every recorded attempt without duplicates.
- [ ] Attempts are grouped into compact turn cards; tool summaries are visible
      under the correct attempt and ordered by tool ordinal without first
      expanding the attempt.
- [ ] Selecting an AI or tool row lazy-loads one shared inline detail surface
      containing that record's request/response/result/error payloads; changing
      selection closes the previous detail and unselected rows do not load bodies.
- [ ] While a run is active, AI and tool summaries advance without per-attempt
      summary requests; only the selected in-flight detail body may poll.
- [ ] Structured objects are pretty-printed, text is escaped, overflow is contained,
      and disclosure controls work by keyboard.
- [ ] Copy controls copy the exact displayed payload and announce success or
      failure inline.
- [ ] Provider errors, failed tools, missing fields, and empty payloads remain
      understandable without exposing an unsafe renderer.

### Usage and Estimated Cost

- [ ] Usage shows aggregate input, cached input, output, reasoning, and total tokens.
- [ ] Attempt count and summed latency agree with the execution audit.
- [ ] Provider/model breakdowns agree with the actual attempts, including retries
      and fallbacks.
- [ ] Cost is always labeled **Estimated cost** with currency and quote time.
- [ ] The frontend performs no independent price calculation.
- [ ] A complete estimate is distinguishable from an incomplete estimate.
- [ ] When an affected real run is available, missing-usage and unpriced call IDs
      are visible and traceable to execution details.
- [ ] Missing cost is not displayed as zero.

## Cross-Cutting UI Review

### Responsive Layout

- [ ] Review every primary route at the recorded desktop viewport.
- [ ] Review every primary route at the recorded mobile viewport or device.
- [ ] Navigation, forms, metadata rails, tables, timelines, code, and article prose
      remain usable without unintended page-width overflow.
- [ ] Important actions remain visible and do not depend on hover.

### Keyboard and Accessibility

- [ ] Complete primary navigation and the generation form using only the keyboard.
- [ ] Focus order follows visual and task order.
- [ ] Focus indicators remain visible on links, buttons, tabs, disclosures, fields,
      dialogs, and scrollable regions.
- [ ] Tabs, dialogs, menus, sheets, and disclosure controls expose their expected
      keyboard behavior and return focus sensibly.
- [ ] Every form field has an accessible name; validation and server errors are
      associated with the relevant field.
- [ ] Loading, submission, copy, polling, and terminal-status feedback is available
      without relying only on color or a transient toast.
- [ ] Status badges and destructive/error colors retain readable contrast.

### Reload, Connectivity, and Errors

- [ ] Directly loading every primary route restores the intended persisted state.
- [ ] Browser back/forward navigation preserves URL-backed filters, tabs, pages, and
      selections.
- [ ] Active generation polling recovers after reload, tab visibility changes, and
      temporary offline/online transitions.
- [ ] Recoverable request failures provide an inline explanation and retry path.
- [ ] Empty lists, missing resources, invalid IDs, archived competitions, stale
      roster observations, partial refreshes, failed generations, and incomplete
      cost data have understandable states.
- [ ] The browser console contains no uncaught exceptions, failed React keys,
      accessibility warnings, or unexpected network loops during the journey.
- [ ] The network panel shows bounded pagination and lazy detail loading rather than
      unbounded or repeated child requests.

## Known Limitations

These are accepted release boundaries unless the review uncovers behavior worse
than described.

- A same-day manual refresh can reuse an earlier matching daily generation
  snapshot. The UI surfaces the distinction but does not redesign snapshot
  identity.
- Generation execution is dispatched by the API process. A hard API-process
  failure can leave work requiring manual recovery because there is no durable
  queue, lease, heartbeat, or automatic resume.
- Sleeper refreshes have no durable lease or heartbeat. A hard process failure
  can leave a `running` row that requires the explicit, cutoff-based
  `reconcile-stale-refreshes` operator command; the API and application startup
  do not automatically classify refreshes as stale.
- Writable simulations, evaluation workspaces, promotion/discard, merge/rebase,
  and historical-memory promotion are intentionally absent.
- The initial application is a trusted local single-operator product without
  authentication, durable per-user ownership, or public publishing.
- An incomplete-cost state depends on recorded provider usage/pricing gaps. If the
  full review database contains no naturally affected run, record that case as not
  observed rather than mutating durable production-like history to manufacture it.

Additional known limitations:

-

## Findings and Outcome

Record defects with a reproducible route, generation or resource ID, expected
behavior, actual behavior, severity, and evidence location. Do not include secrets
or full private model payloads.

| ID     | Severity | Area | Result | Evidence or notes | Disposition |
| ------ | -------- | ---- | ------ | ----------------- | ----------- |
| UI-001 |          |      |        |                   |             |

| Review area                         | Outcome | Notes |
| ----------------------------------- | ------- | ----- |
| Clean bootstrap and automated gates | Pending |       |
| Competition, season, and refresh    | Pending |       |
| Live generation                     | Pending |       |
| Historical read-only backtest       | Pending |       |
| Article and artifacts               | Pending |       |
| Execution and usage                 | Pending |       |
| Responsive and accessibility        | Pending |       |
| Reload, errors, and console         | Pending |       |

Final decision: **Pending / Pass / Pass with accepted limitations / Fail**

Release-blocking findings:

-

Accepted follow-up findings:

-

Reviewer signoff: `____________________________`

Signoff date: `____________________________`

After completion, add a concise result summary and remaining limitations to
`.context/ui/log.md`.
