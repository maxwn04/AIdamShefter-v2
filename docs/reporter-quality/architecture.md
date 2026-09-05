
# Reporter Quality Architecture Proposal

> Scope update: [workstreams.md](workstreams.md) owns current delivery. The
> disposable-database simulator comes first; workspace storage, in-app comparison
> and adoption contracts below are deferred future design options, not simulator
> prerequisites. Evidence and continuity requirements remain relevant.

This describes proposed boundaries, not current implementation.

## Ownership

| Owner | Responsibility |
| --- | --- |
| Frozen data service | Cutoff-bounded facts, identity resolution, calculations, completion and coverage semantics |
| Reporter tool adapters | Model schemas, concise presentation, source handles bound to execution evidence |
| Reporter research state | Claims, evidence bindings, callbacks, story candidates, unresolved questions, audit state |
| Reporter loop | Adaptive research/drafting, bounded correction, submission, same-agent closeout |
| Memory service/managers | Exact identity, pinned retrieval, lifecycle, validated proposals, canonical persistence |
| Generation service | Input selection/sealing, execution and finalization |
| Evaluation/campaign service | Cases, variant lineage, isolated checkpoints, sequential replay and judgments |
| Frontend | Input selection, comparison, evidence inspection, memory commit status, replay controls |

Services use resource managers; routes and workers stay thin. Data and memory
services do not import reporter tools. Simulation invokes ordinary generation
execution and does not introduce a second reporter or bypass finalization.

## Evidence boundary

Extend `ToolExecutionResult(result, metadata)` to data adapters. Visible results
retain facts, short source/lookup handles, units, subject, season/period,
completeness, sent/received perspective and interpretive limitations. Full raw
responses, canonical IDs, hashes and diagnostics remain in saved metadata or a
referenced immutable evidence artifact. An unplayed game or reconstruction caveat
is meaningful evidence, not something to hide merely because it is metadata.
Offer explicit drill-down when default presentation omits detail.

Bind source handles to durable tool calls and selected evidence. Traceability
alone does not verify a claim. Deterministic checks cover identity, values,
direction and period; semantic review covers unsupported inference. Audit the
actual draft, not just an agent-supplied claim list that could omit its errors.
Pin audit results to article and brief revisions. Keep research and drafting
adaptive; do not enforce phases or claim that numeric checks prove all prose.

## Experiment storage: decision required

| Option | Benefit | Cost/risk |
| --- | --- | --- |
| Immutable serialized checkpoints (recommended first) | Fits artifact/manifest seams and isolates canonical rows | Needs ephemeral retrieval parity, explicit lineage and reference remapping |
| Revision-native branches | Potential shared queries and branch browsing | Current introduced/retired visibility is linear; requires branch-safe storage, retrieval and finalization |

Current UI contracts explicitly defer this choice. Compare the options and
reconcile older database/memory docs before implementation. Share typed content,
validation, discovery/ranking and presentation policies across storage paths.
Workspace references resolve within their lineage and explicit pinned base;
adoption maps them to valid canonical references. Do not assign fake canonical
version IDs to uncommitted items.

A case pins facts, memory, request and resolved configuration. Keep prompt and
procedure contents retrievable with hashes, and record actual implementation
identities. Identical inputs do not guarantee deterministic provider output.
Start-empty and reset controls create isolated states; they do not delete
canonical memory. One active workspace with serial comparisons is a reasonable
first limit; simultaneous branching is deferred.

## Story lifecycle

Return run-local memory handles bound to hidden item/version identities. Updates
use handles; creation has an explicit path. Exact revision-scoped lookup must
never depend on a top-N relevance query.

Filter eligible review work before limiting: due callbacks, current events
intersecting arcs, and stale high-value arcs. Due review does not prove a trigger
condition occurred. Record development, payoff/resolution, correction,
unchanged/defer, dormant, or unavailable evidence, with last review, last material
development and next review condition. Keep detailed history in an application
ledger, outside default context.

Preserve origin, linked arcs and counterevidence on updates. Present origin,
latest material development and relevant payoff rather than the first three
references. Persistence and article selection are separate: an unresolved arc
can survive quietly without a weekly mention or rewrite.

Season opening supports historical discovery plus a bounded continuity bundle:
durable context, unresolved arcs with continuing stakes, due cross-season
callbacks and relevant landmark resolutions. Show season as well as week;
exclude routine old memories without current relevance.

## Replay and adoption

Start with a four-checkpoint pilot spanning origin, quiet interval, payoff or
contradiction, and season transition. Then cover every relevant league week and
playoffs; do not assume week 18 contains played games. Each step consumes a
sealed cutoff-bounded snapshot and the previous successful memory checkpoint.
Pin per-step snapshots in advance or derive them from one sealed source set;
retry must not refresh into different data.

Pause/cancel and budget policy sit between bounded generation calls. Resume the
first uncommitted step with an idempotent identity. Failure leaves the current
checkpoint intact. This needs a small campaign coordinator, not a general
workflow engine initially.

Retrospective reconstruction uses later-fetched historical responses and has
documented limits on volatile fields. Faithful historical replay separately
requires observations available at its knowledge cutoff; missing coverage must
be reported. Neither mode may implicitly read later canonical memory.

Review outcomes, unresolved arcs, corrections, stale triggers, franchise links
and unsupported claims before seed adoption. Initially target empty canonical
memory. An empty replay input and a canonical concurrency token are distinct:
an unchanged nonempty head does not authorize replacing its memories. Nonempty
adoption needs an additive import/conflict policy or a separate rebuild contract.

## Measured cleanup

Extract tool execution/recording, transcript construction and reporter completion
policy along existing invariants. Preserve cancellation, exact telemetry,
artifact conflicts and atomic closeout. Independent reads may run together;
conflicting mutations need deliberate ordering.

Measure context contributions first. Reduce repeated full articles and broad
tool outputs before transcript compaction. Later assemble context from assignment,
supported brief, current article, unresolved questions, selected evidence and
recent turns. Preserve corrections and tool-call/result protocol integrity;
older payloads remain retrievable from audit storage.

Reconcile research-pipeline docs describing a retired fact bridge/separate
curator with memory-refactor docs describing same-agent closeout. Replace legacy
equivalence constraints with backend product contracts as affected code changes.
