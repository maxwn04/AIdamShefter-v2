# Memory Service Decision Log

This is an append-only record for decisions that constrain the application
memory service, its caller-facing contracts, or its implementation boundaries.
Canonical storage decisions remain in [`../database/log.md`](../database/log.md).

## Entry Format

Each entry records:

- a stable decision identifier;
- the date and status;
- the source and decision;
- consequences for implementation and downstream consumers.

When a later entry explicitly supersedes an earlier one, the later entry is the
implementation contract. Earlier entries remain to preserve the reasoning
history.

## Decisions

### MEM-001 — Implement memory as a modular-monolith service

**Date:** 2026-08-09
**Status:** Settled
**Source:** Platform architecture and service-boundary review

Memory is a cohesive backend service inside the existing AIdam deployment. It
uses the shared PostgreSQL database and migration history. It is not a separate
network service, database, or deployable.

**Consequences:**

- The primary service boundary is a typed Python contract.
- FastAPI, reporter tools, worker, and CLI code are adapters.
- Do not introduce HTTP calls or serialization between backend services.
- Preserve package boundaries so a future extraction remains possible only if
  operational evidence justifies it.

### MEM-002 — Expose narrow reader, writer, inspector, and admin capabilities

**Date:** 2026-08-09
**Status:** Settled
**Source:** Service-contract review

One concrete `MemoryService` may compose the memory capability, but consumers
depend on the narrow contract they require: revision-pinned reading, canonical
writing, historical inspection, or projection administration.

**Consequences:**

- Reporter tools receive only a pinned reader.
- Generation finalization receives the canonical writer.
- UI/audit surfaces may receive the inspector.
- Maintenance commands receive projection administration.
- A broad service facade must not become ambient global state or a service
  locator.

### MEM-003 — Make generation-time revision scope capability-bound

**Date:** 2026-08-09
**Status:** Settled
**Source:** Historical-leakage review

The generation service resolves an exact canonical revision and constructs a
lightweight `PinnedMemoryReader` for the reporter. Reporter tool arguments do not
accept competition or revision overrides.

**Consequences:**

- Every candidate query, exact-version read, and stable-item read enforces the
  same competition and revision.
- The pinned reader carries identifiers only; it does not hold a database
  session open during reporter execution.
- Historical visibility cannot depend on the current revision pointer or on
  search-document contents alone.

### MEM-004 — Keep resource objects as the public application representation

**Date:** 2026-08-09
**Status:** Settled
**Source:** Application-contract review

Routes, services, reporter tools, and workers exchange typed memory resource
objects and stable result types. ORM rows, SQLAlchemy sessions, database JSON
shapes, and search-document records remain internal to the resource manager and
retrieval implementation.

**Consequences:**

- API schemas may wrap or present resource objects but do not replace them as
  the backend contract.
- Content-schema conversion is centralized with memory resource objects.
- Storage changes that preserve the resource contract do not require caller
  changes.

### MEM-005 — Persist complete typed replacements

**Date:** 2026-08-09
**Status:** Settled
**Source:** DB-031 and application mutation review

Creates and replacements contain one complete kind-specific content object.
Archiving, resolving, firing, and superseding create new complete versions. The
canonical mutation contract does not expose partial patches or generic
relationship operations.

**Consequences:**

- Omitted owned subjects, evidence, or relationships mean an empty collection,
  not “leave unchanged.”
- Patch-oriented user interfaces must assemble and validate a complete
  replacement before calling the service.
- Adding a new event type extends a discriminated content union rather than a
  generic event bag.

### MEM-006 — Let the memory manager own the canonical transaction

**Date:** 2026-08-09
**Status:** Settled
**Source:** Transaction-boundary review

The memory resource manager owns the single short transaction that locks the
current revision, validates persisted references and optimistic expectations,
creates one revision, writes complete versions, retires replaced versions,
inserts search documents, verifies resulting state, and advances the pointer.

**Consequences:**

- Services do not receive or pass SQLAlchemy sessions.
- No table-by-table public CRUD or generic repository is introduced.
- Cross-resource validation inside the transaction uses narrow helpers that do
  not open or commit sessions.
- Model calls, provider calls, embeddings, filesystem work, and reporter
  execution finish outside the transaction.

### MEM-007 — Separate candidate discovery from canonical hydration

**Date:** 2026-08-09
**Status:** Settled
**Source:** DB-031 and retrieval review

Search documents produce compact, revision-eligible candidate version IDs and
named match reasons. Selected candidates are then batch-hydrated from canonical
typed versions before crossing the service boundary.

**Consequences:**

- Search documents are never returned as authoritative memory.
- Competition and pinned-revision visibility are applied before ranking.
- Ranking uses named components or rank fusion rather than combining unrelated
  scores as if they shared one scale.
- Projection corruption can be repaired without changing canonical history.

### MEM-008 — Keep canonical commit authority outside reporter tools

**Date:** 2026-08-09
**Status:** Settled
**Source:** Generation-lifecycle review

The reporter may emit a typed mutation proposal. Only the generation service,
after reporter execution and proposal acceptance, invokes the canonical writer
with the pinned base revision and producing-generation provenance.

**Consequences:**

- Reporter tools cannot mutate memory mid-run or change what the same generation
  is allowed to retrieve.
- All model work completes before the canonical transaction.
- Stale canonical state causes a typed failure and rerun; it never creates a
  sibling state.

### MEM-009 — Treat projection rebuild as an administrative operation

**Date:** 2026-08-09
**Status:** Settled
**Source:** Projection lifecycle review

Normal canonical mutations build search documents synchronously and atomically.
Inspection and full rebuild are separate operator capabilities that read
canonical versions and rewrite only derived state.

**Consequences:**

- Rebuild does not create canonical revisions.
- The baseline can expose rebuild through a synchronous CLI.
- Durable jobs, leases, and embedding backfill orchestration remain deferred.
- Rebuild must decode every retained content-schema version and be deterministic
  for a fixed builder version.

### MEM-010 — Keep factual verification outside the memory service

**Date:** 2026-08-09
**Status:** Settled
**Source:** Service ownership review

Memory retrieval returns narrative context and provenance. It does not decide
that a remembered claim is true for the current article. The generation and
reporter workflow verifies claims against its frozen, cutoff-safe Sleeper
snapshot.

**Consequences:**

- The memory service does not depend on or query the reporter's SQLite factual
  snapshot.
- Retrieval ranking may use memory metadata but cannot promote memory to
  canonical football truth.
- Verification evidence remains visible to article generation and audit through
  reporting tool calls and artifacts.

### MEM-011 — Treat capability contracts as views, not mandatory classes

**Date:** 2026-08-09
**Status:** Settled; clarifies MEM-002 and MEM-003
**Source:** User feedback on implementation fragmentation

Reader, writer, inspector, and projection-admin protocols describe which
operations a consumer may use. They do not each require a separate concrete
coordinator. The baseline uses one `MemoryService`, one `MemoryManager`, and a
small immutable `PinnedMemoryReader` that the service creates for a validated
revision scope.

The pinned reader delegates back to the service's internal retrieval pipeline
with that fixed scope. The retrieval pipeline does not create or own pinned
readers and does not begin as a stateful class.

**Consequences:**

- Do not pre-create coordinator classes or empty packages for retrieval,
  mutation, inspection, or projection administration.
- Begin with service methods and small internal functions; split them only when
  they acquire distinct state, dependencies, or substantial complexity.
- Keep the pinned reader because revision-scope safety justifies that wrapper.
- Protocols remain useful for dependency typing and tests without dictating
  runtime object count.

### MEM-012 — Keep inspection and projection administration intentionally small

**Date:** 2026-08-09
**Status:** Settled
**Source:** User feedback on unknown UI and user experience

The baseline inspector supports only canonical viewing: listing items at the
current or selected revision, viewing an item, viewing item history, and listing
revisions with basic provenance. Projection administration supports only status
and deterministic rebuild of the derived search-document index.

**Consequences:**

- Do not build advanced diffs, analytics, bulk editing, restoration, ranking
  tuning, or transformative memory operations before a concrete UX requires
  them.
- Projection status reports only actionable builder-version and missing/stale
  document information.
- Rebuild is initially a synchronous CLI operation; a projection API and durable
  job workflow are deferred.
- The inspector and projection-admin protocols may be capability views on the
  same `MemoryService` rather than concrete classes.

### MEM-013 — Keep workspace promotion outside inspection and projection admin

**Date:** 2026-08-09
**Status:** Settled
**Source:** Boundary clarification

Promotion means fast-forwarding a reporting-owned evaluation workspace into one
new canonical memory revision. It does not mean search-projection rebuild or
historical restoration.

**Consequences:**

- The evaluation service owns promotion because it validates and updates the
  workspace and its final artifact.
- The memory module supplies a narrow same-transaction helper for applying the
  validated final diff when the workspace base remains current.
- Promotion supports no merge, rebase, arbitrary historical restore, or content
  transformation modes.

### MEM-014 — Give promotion one cross-resource transaction owner

**Date:** 2026-08-09
**Status:** Settled; clarifies MEM-006 and MEM-013
**Source:** Independent strategic-programming review

`EvaluationService.promote_workspace` owns the public workflow, while the
evaluation-workspace manager owns its one private transaction. That transaction
locks and updates the reporting workspace and invokes a session-scoped internal
memory command to create the fast-forward canonical revision.

**Consequences:**

- `MemoryManager` owns ordinary canonical mutation transactions but does not open
  or commit the promotion transaction.
- The session-scoped memory command is private, does not delegate to a public
  service, and enforces the canonical base/current invariant itself.
- Public services, routes, and workers never receive or pass database sessions.
- Retrying an already promoted workspace returns its existing promoted revision.

### MEM-015 — Use one authoritative search-document builder

**Date:** 2026-08-09
**Status:** Settled
**Source:** Independent duplication and information-hiding review

`backend/resources/memory/search_documents.py` owns one public dispatcher over
the discriminated typed memory union. Private per-kind functions implement the
actual flattening. Canonical mutation and full rebuild call that same dispatcher;
the manager persists its output and retrieval never rebuilds documents.

**Consequences:**

- Mutation and rebuild cannot drift into separate document policies.
- Builder inputs come only from immutable version content. Stored display-name
  snapshots may be indexed; current external names are never resolved during a
  rebuild.
- The builder version and projection-input hash, including immutable content,
  context-note identity, season, and week, fully identify deterministic output.
- Golden tests invoke the same dispatcher through mutation and rebuild paths.

### MEM-016 — Derive mutation context and use one concurrency token

**Date:** 2026-08-09
**Status:** Settled
**Source:** Independent complexity and error-design review

A public mutation bundle supplies only its producing generation ID and typed
operations. The memory manager derives competition, season, week, knowledge
cutoff, and the pinned input revision from that generation inside the mutation
operation. The generation's base revision is the only optimistic concurrency
token; replacements do not supply an expected item revision.

**Consequences:**

- Callers cannot submit inconsistent copies of persisted generation facts.
- Under the locked base revision, each target item's visible version is
  unambiguous.
- `StaleItemRevision` is removed from the public error contract; a changed
  canonical base produces `StaleCanonicalRevision`.
- Empty bundles, identical replacements, and already-represented transitions
  return `NoChange` without creating a revision.
- Retrying a generation that already committed returns the existing committed
  revision rather than a stale-write error.

### MEM-017 — Keep consumer ports static and mask index repair internally

**Date:** 2026-08-09
**Status:** Settled; clarifies MEM-011 and MEM-012
**Source:** Independent deep-module review

Reader, writer, inspector, and search-index-admin protocols are static consumer
ports used for dependency typing. They are not runtime authorization objects.
Composition decides which port a consumer receives; only `PinnedMemoryReader` is
an actual scoped capability because it carries an enforced revision invariant.

**Consequences:**

- Do not claim `MemoryService` itself prevents a holder from calling its other
  methods.
- The initial implementation does not add one forwarding class per port.
- Search-index maintenance uses explicit `search_index_status` and
  `rebuild_search_index` names rather than generic projection verbs.
- Ordinary retrieval masks missing or stale index rows with a bounded canonical
  fallback. `ProjectionUnavailable` is not a caller-facing error.

### MEM-018 — Implement the service as a six-layer GitHub PR stack

**Date:** 2026-08-09
**Status:** Settled
**Source:** User direction and implementation planning

Build the memory application layer as six incremental branches managed by
`gh stack`: contracts, canonical persistence/search documents, canonical
mutation, pinned retrieval/inspection, composition/adapters, and reporting-owned
workspace promotion.

**Consequences:**

- The stack is based on `main@32b2d88`, which includes the FastAPI skeleton.
- Each PR must remain independently reviewable and testable against its parent.
- `docs/memory/status.md` is the live path-ownership and completion ledger for
  parallel agents.
- Shared files are changed by one assigned owner at a time and integrated by
  `root`.
- `gh stack submit --auto` publishes draft PRs after local verification and
  design review; Graphite commands are not used for this stack.

### MEM-019 — Start with a narrow version-one content vocabulary

**Date:** 2026-08-09
**Status:** Settled
**Source:** Contract implementation

The first resource contract supports storyline subject roles `focus` and
`counterparty`, fact subject role `subject`, event payloads for trade, matchup,
waiver, and standings changes, and trigger conditions for week, datetime, and
event callbacks.

**Consequences:**

- New roles and discriminators extend the centralized unions and validators in
  `backend/resources/memory/objects.py`; callers do not submit arbitrary role or
  payload bags.
- Entity display names are immutable version-local label snapshots.
- Context-note typed versions carry their stable scope/key identity so the sole
  search-document builder can rebuild without current-name or database lookups.
- This vocabulary is deliberately sufficient for the current reporter behavior,
  not an exhaustive fantasy-football ontology.

### MEM-020 — Let the service pin current memory in one operation

**Date:** 2026-08-09
**Status:** Settled
**Source:** Independent caller-complexity review

`MemoryService.pin_current(competition_id)` resolves the current canonical
revision and returns its `PinnedMemoryReader` in one service operation.
`at_revision(revision_id)` remains available when a generation or audit record
already stores an exact revision.

**Consequences:**

- Callers do not coordinate `current_revision` followed by `at_revision`, which
  could accidentally pin a different revision after a concurrent write.
- The service, which owns revision resolution, also owns construction of the
  invariant-carrying reader.
- The retrieval pipeline still neither constructs readers nor exposes revision
  overrides.
- No generic `shared.py` module is reserved for future promotion code; the
  private promotion command is named only when its concrete invariant exists.

### MEM-021 — Make boundary values deeply immutable and references directly usable

**Date:** 2026-08-09
**Status:** Settled
**Source:** Independent contract and information-hiding review

Typed memory uses tuples, frozen sets, and recursively immutable JSON objects at
the application boundary. Create operations generate both their stable item ID
and first immutable version ID when constructed. Retrieval filters use
role-free entity keys rather than authored entity references.

**Consequences:**

- Deterministic hashes and search documents cannot change because a caller
  mutates a nested list or JSON object after validation.
- A create later in the same mutation bundle may use an earlier create's
  generated version ID for evidence or item ID for a stable relationship.
- Client keys remain correlation labels and do not become a second domain
  reference vocabulary.
- Retrieval callers identify an entity without inventing an authoring role or
  label snapshot.
- Content-decoder errors contain sanitized JSON-safe validation details rather
  than Pydantic exception objects or documentation URLs.

### MEM-022 — Normalize mutations against their pinned generation input

**Date:** 2026-08-09
**Status:** Settled
**Source:** Independent concurrency and error-design review

Mutation intent is first evaluated against the producing generation's pinned
input revision, never against a newer current pointer. Empty or identical input
therefore returns that pinned revision. If canonical state advanced, the manager
evaluates the same unresolved transition against current state: an already
represented transition is a no-op, while any remaining transition is stale.

**Consequences:**

- A stale generation cannot silently adopt unrelated newer memory as the result
  of an empty or base-identical bundle.
- Callers do not supply retry flags or implement race-specific branching.
- First commits and retries return one payload-independent canonical result,
  ordered by stable item and version identity.
- A create result carries its client correlation key; a replacement result does
  not incorrectly reuse the item's original creation key.

### MEM-023 — Pair one content codec with a stored-state invariant

**Date:** 2026-08-09
**Status:** Settled
**Source:** Independent deep-module and information-hiding review

`backend/resources/memory/content_codec.py` owns both directions of every
schema-versioned typed-content mapping. `MemoryManager` continues to own the
aggregate transaction, but it decodes the rows it just persisted and verifies
the resulting visible-state hash before advancing the current pointer.

**Consequences:**

- Adding or retaining a content schema version has one codec registry entry
  rather than separate manager read and write switch statements.
- Unsupported stored schemas and state-hash mismatches are named internal
  operational faults, not caller input errors.
- Source-backed facts and events require a tool-call or API-request receipt;
  the manager validates that receipt in the generation or competition scope.
- Any encoding drift, projection failure, or hash mismatch rolls back the whole
  canonical mutation.

### MEM-024 — Keep retrieval policy cohesive and pagination revision-safe

**Date:** 2026-08-09
**Status:** Settled
**Source:** Independent deep-module and caller-complexity review

`MemoryService` is the single owner of retrieval weighting, reason vocabulary,
deduplication, hydration order, and the final result limit. `MemoryManager`
returns bounded raw candidate signals, reserving capacity independently for
lexical, entity, evidence-version, and related-item matches. Primary and bounded
fallback discovery feed the same service policy.

`MemoryService` also creates the immutable pinned reader. The reader retains one
validated revision, delegates ranked retrieval to the service, and performs
exact visible-item/version reads through the captured narrow manager. It is a
scope capability, not a retrieval coordinator.

**Consequences:**

- No `RetrievalCoordinator`, forwarding-only admin class, or duplicate retrieval
  protocol/module is introduced.
- Search-index status/rebuild and canonical mutation are structural ports
  satisfied directly by the deep manager; inspection remains a narrow service
  view limited to viewing, history, and revisions.
- Exact evidence and related-item signals work in both primary and degraded
  paths without kind-specific service methods.
- Result contracts expose typed matched entities and stable reasons, not search
  key strings or internal score-component maps.
- Opaque item cursors contain the resolved revision; later pages cannot drift to
  a newer current state, and invalid cursor/query inputs use stable memory
  errors.

## Pending Decisions

- Default retrieval and evidence-expansion limits.
