# Typed Memory Implementation Status

## Current Phase

**Active layer:** `memory-12` complete; `memory-13` is next
**Current branch:** `codex/memory-12-api`
**Stack:** `main` <- `memory-0` <- `memory-1` <- `memory-2` <- `memory-3` <- `memory-4` <- `memory-5` <- `memory-6` <- `memory-7` <- `memory-8` <- `memory-9` <- `memory-10` <- `memory-11` <- `memory-12`
**Publication:** `memory-12` is published as PR #120 atop `memory-11` (PR #119).

This file is the coordination ledger for the typed-memory application stack.
The completed database stack remains tracked separately in
[`docs/database/status.md`](../database/status.md).

## Layer Ledger

| Layer | Branch | State | Owner | Verification | Commit / PR |
| --- | --- | --- | --- | --- | --- |
| `memory-0` implementation plan | `codex/memory-0-implementation-plan` | Complete | `root` | Documentation review | `45477b0`; draft PR #106 |
| `memory-1` ORM modules | `codex/memory-1-orm-modules` | Complete | `root` | Schema-preserving split already committed | `b7f758c`; draft PR #107 |
| `memory-2` contracts | `codex/memory-2-contracts` | Complete | `root` + `contracts_audit` | 29 focused contract tests; backend: 52 passed, 49 PostgreSQL tests skipped | `e16e5ce`; draft PR #109 |
| `memory-3` revisions | `codex/memory-3-revisions` | Complete | `root` + `contracts_audit` + reviewers | 3 focused PostgreSQL tests; backend: 104 passed; basedpyright: clean | `d70cb4c`; draft PR #110 |
| `memory-4` facts | `codex/memory-4-facts` | Complete | `root` + `plan_mapper` + `stack_audit` + `contracts_audit` | 8 focused tests; memory: 40 passed; backend: 112 passed; basedpyright: clean | `5b71628`; draft PR #111 |
| `memory-5` events | `codex/memory-5-events` | Complete | `root` | 9 focused event tests; memory: 49 passed; backend: 121 passed; basedpyright 1.39.10 found no new errors and 16 pre-existing backend errors | Active branch head; draft PR #112 |
| `memory-6` storylines | `codex/memory-6-storylines` | Complete | `root` | 7 focused storyline tests; memory: 56 passed; backend: 128 passed; basedpyright found no new errors and 16 pre-existing backend errors | `e4c7831`; PR #114 |
| `memory-7` triggers | `codex/memory-7-triggers` | Complete | `root` | 8 focused trigger tests; memory: 64 passed; backend: 136 passed; basedpyright found no new errors and 16 pre-existing backend errors | `5788729`; PR #113 |
| `memory-8` context notes | `codex/memory-8-context-notes` | Complete | `root` | 9 focused context-note tests; memory: 73 passed; backend: 145 passed; basedpyright found no new errors and the same 16 pre-existing backend errors | Active branch head; PR #115 |
| `memory-9` mutation bundles | `codex/memory-9-mutation-bundles` | Complete | `root` | 6 focused service tests; memory: 79 passed; backend: 151 passed; basedpyright found no new errors and the same 16 pre-existing backend errors | `0260366`; PR #117 |
| `memory-10` search projection | `codex/memory-10-search-projection` | Complete | `root` | 5 focused PostgreSQL tests; memory: 84 passed; backend: 156 passed; basedpyright found no new errors and the same 16 pre-existing backend errors | `915ddf4`; PR #118 |
| `memory-11` retrieval | `codex/memory-11-retrieval` | Complete | `root` | 7 focused PostgreSQL tests; memory: 91 passed; backend: 163 passed; basedpyright found no new errors and the same 16 pre-existing backend errors | `a8a7250`; PR #119 |
| `memory-12` HTTP API | `codex/memory-12-api` | Complete | `root` | 10 focused API/composition tests; memory + API: 107 passed; backend: 173 passed; focused basedpyright clean and full backend retains the same 16 pre-existing errors; Ruff clean | `29474c4`; PR #120 |
| `memory-13` reporter retrieval | `codex/memory-13-reporter-retrieval` | Pending | Unassigned | Not started | — |
| `memory-14` reporter mutations | `codex/memory-14-reporter-mutations` | Pending | Unassigned | Not started | — |

## Coordination Rules

- Work on one stack layer at a time and keep each layer independently testable.
- Keep tests lean and contract-based: cover behavior that materially increases
  confidence, not implementation details or exhaustive edge-case permutations.
- Record an active owner and assigned paths before delegated edits begin.
- Do not edit paths owned by another active implementer.
- Update verification, commit, and PR state before advancing to the next layer.
- Record uncovered design decisions here rather than resolving them implicitly.
- Keep the integration tail on the same stack unless the optional split after
  `memory-11` is explicitly approved.

## `memory-12` Assignments

| Owner | Assigned paths | Work |
| --- | --- | --- |
| `root` | `backend/api/routes/memory/` (including co-located transport models), memory API dependencies/error translation, composition wiring, API tests, `docs/memory/` | Competition-scoped revision/resource reads, hydrated search, complete create/replacement writes, stable typed error responses, OpenAPI coverage, verification, and coordination ownership |

## `memory-11` Assignments

| Owner | Assigned paths | Work |
| --- | --- | --- |
| `root` | `backend/services/memory/retrieval_service.py`, event/storyline visible reads, retrieval tests, typed generation-context boundary, `docs/memory/` | Revision-pinned canonical hydration, one-hop typed exact/stable reference sidecars, projection-integrity enforcement, public retrieval contracts, verification, and coordination ownership |

## `memory-10` Assignments

| Owner | Assigned paths | Work |
| --- | --- | --- |
| `root` | `backend/resources/memory/search_documents/`, search-document manager tests, `docs/memory/` | Revision-grounded candidate discovery, deterministic additive scoring, atomic competition-scoped rebuilds, public projection contracts, verification, and coordination ownership |

## `memory-9` Assignments

| Owner | Assigned paths | Work |
| --- | --- | --- |
| `root` | `backend/services/memory/`, canonical revision write orchestration, resource-local state readers/persisters, mutation-service tests, `docs/memory/status.md` | Generation-scoped typed proposal buffer, public mutation service, batch reference validation, same-bundle identity resolution, atomic multi-resource persistence, resulting-state hashing, stale-writer and rollback coverage |

## `memory-8` Assignments

| Owner | Assigned paths | Work |
| --- | --- | --- |
| `root` | `backend/resources/memory/context_notes/`, context-note projection builder/exports, context-note tests, `docs/memory/status.md`, context-note builder signature in `docs/memory/retrieval.md` | Context-note aggregate hydration, stable scope/key validation and persistence, v1 codec, deterministic projection, lean verification, and coordination ownership |

## `memory-7` Assignments

| Owner | Assigned paths | Work |
| --- | --- | --- |
| `root` | `backend/resources/memory/triggers/`, trigger projection builder/exports, trigger tests, `docs/memory/status.md` | Trigger manager reads, v1 codec, stable-target and rematch-entity validation, canonical-write helpers, deterministic projection, lean verification, and coordination ownership |

## `memory-6` Assignments

| Owner | Assigned paths | Work |
| --- | --- | --- |
| `root` | shared entity validation, `backend/resources/memory/storylines/`, storyline projection builder/exports, storyline tests, `docs/memory/status.md` | Storyline manager reads, v1 codec, exact evidence and stable relationship validation, canonical-write helpers, deterministic projection, verification, and coordination ownership |

## `memory-5` Assignments

| Owner | Assigned paths | Work |
| --- | --- | --- |
| `root` | `backend/resources/memory/events/`, event projection builder/exports, shared receipt validation, event tests, `docs/memory/status.md` | Event manager reads, v1 codec, validation, canonical-write helpers, deterministic projection, verification, and coordination ownership |

## `memory-4` Assignments

| Owner | Assigned paths | Work |
| --- | --- | --- |
| `root` | `backend/resources/memory/facts/`, revision transaction integration outside `revisions/hashing.py`, dependency metadata, `docs/memory/status.md` | Fact manager reads, codec, validation, basic SQL helpers, dependency and coordination ownership |
| `plan_mapper` | `backend/resources/memory/revisions/hashing.py` | Confirmed deterministic CBOR state serializer and digest implementation |
| `stack_audit` | `backend/resources/memory/search_documents/` | Identity-free projection contract, fact builder, and package-internal ORM persistence adapter |
| `contracts_audit` | `backend/tests/resources/memory/test_fact_manager.py`, `backend/tests/resources/memory/test_fact_search_builder.py`, `backend/tests/resources/memory/test_revision_hashing.py` | Lean public-contract, golden-vector, and atomic-write tests |

Agents must not edit another owner's paths. After implementation, review work is
read-only and cross-assigned so each major boundary receives an independent
design and correctness pass.

## `memory-3` Assignments

| Owner | Assigned paths | Work |
| --- | --- | --- |
| `root` | `backend/resources/memory/revisions/`, revision exports, `docs/memory/status.md` | Complete: revision resource boundary and manager implementation |
| `contracts_audit` | `backend/tests/resources/memory/test_revision_manager.py` | Complete: lean PostgreSQL contract tests and seeded query proofs |
| `plan_mapper` | Read-only | Complete: public-boundary and information-leakage review |
| `stack_audit` | Read-only | Complete: PostgreSQL/SQLAlchemy and concurrency-boundary review |

## Open Design Decisions

1. **`memory-3` query-proof boundary.** The layer requires storyline entity and
   exact-evidence query proofs, but `RevisionManager` cannot contain kind-specific
   SQL and `StorylineManager` is scheduled for `memory-6`. Recommended default:
   prove the PostgreSQL query shapes with seeded acceptance tests in `memory-3`
   while keeping public storyline reads in `memory-6`. This default is being
   applied locally pending a user override.
2. **Canonical state hashing (resolved for `memory-4`).** The user approved
   `sha256-cbor-v1` over deterministic RFC 8949 CBOR. The revision package owns
   a versioned competition-state envelope; callers cannot supply hashes.
   Exact fields, normalization, exclusions, empty-state behavior, and golden
   vectors are recorded by the implementation and tests in this layer.
3. **Search-document builder contract (resolved for `memory-4`).** Builders
   return an identity-free derived projection. Version, item, competition,
   season/week, timestamps, and database search-vector concerns remain inside
   the package-internal persistence adapter. Public query and rebuild APIs stay
   deferred to `memory-10`.
4. **Projection rebuild ownership (resolved for `memory-10`).**
   `SearchDocumentManager.rebuild()` is the competition-scoped application
   capability. HTTP/CLI exposure remains deferred, and canonical mutation
   ownership remains exclusively with `RevisionManager`.
5. **Integration-tail stack split.** Layers `memory-12` through `memory-14` may
   become a second stack based on `memory-11`, but only with explicit approval.
6. **Public mutation ownership (resolved for `memory-4`).** Public complete
   create and replacement operations are deferred to `MemoryMutationService` in
   `memory-9`; typed managers do not expose standalone mutation methods. Resource
   managers own scoped reads, codecs, validation, and package-internal basic SQL
   helpers. The service owns bundle and business semantics and defines the
   atomic unit of work, while `RevisionManager` owns its enclosed database
   transaction, revision locking, state hash, pointer advance, and commit or
   rollback. Sessions and ORM rows do not cross either public boundary.

## `memory-4` Boundary Notes

- Canonical state hashes are `sha256-cbor-v1:<64 lowercase hex>` over RFC 8949
  deterministic CBOR. Each resource codec supplies an explicit retained-schema
  payload; hashing never serializes an upgraded current-view model and callers
  never supply a digest.
- The state envelope contains its format, competition UUID, and visible items
  sorted by item/version UUID. Items contain stable identity, exact version
  identity and revision number, stored schema version, season/week/occurrence,
  optional context-note identity, and exact stored content. Revision mechanics,
  DB timestamps, creation provenance, change reason, and projections are
  excluded.
- UUIDs use lowercase hyphenated text; aware datetimes normalize to UTC with
  six fractional digits and `Z`; mapping order is canonicalized; finite numeric
  types and exact list order are preserved. The empty-state and Fact-v1 bytes
  are locked by golden vectors. The `cbor2` protocol dependency is major-bound.
- Fact search projections are identity-free and rebuildable. Their derived
  content hash normalizes the order-insensitive subject/origin collections,
  while the confirmed canonical state protocol preserves exact stored list
  order. Thus an order-only source rewrite may keep the same projection but is
  still a distinct canonical stored state.
- `season_roster` subjects use the retrieval design's documented `roster:`
  flattened entity key; the typed source discriminator remains
  `season_roster`.
- Resource-local helpers bind validated competition scope, require typed event
  origins, validate entity and receipt scope, enforce expected item revision on
  replacement, and insert fact content plus its search projection in the
  caller's transaction. Revision-owned envelope persistence hides the ORM's
  explicit revision/item/version flush ordering.
- `FactManager.exact` hydrates retired immutable versions without applying
  current visibility. Fact item history is explicitly newest-first, matching
  canonical revision history ordering.
- Public fact create/replace is intentionally absent from this layer. The
  resource-local validation and SQL helpers are composed by
  `MemoryMutationService` in `memory-9`, including the one-proposal case.

## `memory-5` Boundary Notes

- `EventManager` exposes competition-scoped exact-version hydration and
  newest-first item history. Exact reads include retired immutable versions.
- Event v1 codecs preserve the complete `trade` or `matchup` discriminator and
  payload. Retained canonical state content preserves exact asset order, while
  the derived projection normalizes the order-insensitive asset collection.
- Trade validation requires both franchises in scope, globally known players,
  competition-scoped normalized draft picks, and valid typed receipts. Matchup
  validation requires both franchises in scope; `sleeper_matchup_id` remains an
  opaque nonblank external identifier and does not require a normalized row.
- Reporting tool-call and Sleeper API-request validation now live in one shared
  package helper used unchanged by both facts and events.
- Event projections contain status, salience, deterministic franchise/player/
  draft-pick keys, and payload-specific lexical text. Receipt IDs and canonical
  persistence identity do not enter searchable text, but complete content still
  contributes to the projection content hash.
- Resource-local create/replacement preparation validates item kind, scope,
  expected revision, envelope persistence, and schema agreement. Typed content
  and its search projection remain part of the caller-owned canonical
  transaction. Public mutation operations remain deferred to `memory-9`.

## `memory-6` Boundary Notes

- `StorylineManager` exposes competition-scoped exact-version hydration and
  newest-first item history. Exact reads include retired immutable versions and
  do not disclose cross-competition targets.
- Storyline v1 codecs preserve complete subjects, exact fact/event evidence,
  stable related-storyline references, callback conditions, and resolution
  summaries. Retained canonical state preserves exact list order.
- Shared entity-reference validation now owns the identical franchise,
  season-roster, season, player, and Sleeper-user scope rules used by facts and
  storylines; fact behavior is unchanged.
- Evidence validation targets exact immutable fact/event versions, including
  retired history, and verifies declared kind, typed-row presence, and
  competition scope. Related storyline validation targets stable same-scope
  storyline items without imposing an undocumented self-reference policy.
- Storyline projections normalize order-insensitive subjects, evidence,
  relationships, and tags. They include typed entity keys, exact evidence IDs,
  stable related-item IDs, and deterministic narrative, participant, evidence,
  relationship, callback, and resolution text.
- Resource-local create/replacement helpers enforce complete replacement,
  expected item revision, persisted envelope ordering, schema agreement, and
  atomic typed-row plus projection insertion. Public mutations remain deferred
  to `memory-9`.

## `memory-7` Boundary Notes

- `TriggerManager` exposes competition-scoped exact-version hydration and
  newest-first item history. Exact reads include retired immutable versions and
  do not disclose cross-competition targets.
- Trigger v1 codecs retain the complete status, fire policy, scheduling,
  stable targets, discriminated condition, and resolution payload. Canonical
  state hashing preserves exact stored rematch-franchise order.
- Database-backed validation requires target seasons and rematch franchises to
  exist in the competition. Optional storyline and origin-event references
  target stable same-scope items of their declared kinds; current visibility is
  irrelevant. Existing typed-contract rules remain the sole source of pure
  trigger-condition validation.
- Trigger projections include status, rematch franchise and season entity keys,
  stable storyline/event item IDs, and deterministic type, policy, schedule,
  condition, and resolution text. The unordered rematch pair is normalized for
  projection equality and hashing without changing canonical stored ordering.
- Resource-local create/replacement helpers enforce complete replacement,
  expected item revision, persisted envelope ordering, schema agreement, and
  atomic typed-row plus projection insertion. Public mutations remain deferred
  to `memory-9`; migrations, retrieval behavior, and reporter integration remain
  outside this layer.

## `memory-8` Boundary Notes

- `ContextNoteManager` hydrates the stable scope/key identity and immutable
  versioned content as one competition-scoped aggregate. Exact reads include
  retired versions, and history is newest-first without disclosing another
  competition's notes.
- Create preparation accepts a typed competition, competition-season, or
  franchise identity plus complete v1 content. Season and franchise targets
  must exist in the manager's competition; competition-scoped notes require no
  additional target lookup.
- Scope and note key are inserted once beside the stable memory item.
  Replacements resolve that stored identity and accept only new complete
  content, so a version change cannot silently move or rename the note.
- Context-note projections include status, normalized tags, stable scope and
  note key, narrative, outlook, and season/franchise entity keys. The derived
  content hash covers both stable identity and complete content because the
  context note is one resource aggregate.
- Resource-local helpers preserve caller-owned transaction boundaries and
  atomically persist stable identity, typed content, and derived projection.
  Public mutation orchestration, uniqueness conflict translation, retrieval,
  and reporter integration remain deferred to later layers.

## `memory-9` Boundary Notes

- `GenerationMemoryContext` owns an in-memory, generation-scoped proposal
  buffer. It preallocates canonical item and version UUIDs, returns those typed
  proposal references to callers, keeps every search pinned to the immutable
  input revision, and yields its completed bundle exactly once.
- `MemoryMutationService` exposes complete create and replacement operations for
  every implemented kind and accepts a completed multi-resource bundle. It
  translates proposals into opaque resource-local persisters without importing
  SQLAlchemy sessions or ORM models.
- Proposal-local item and version UUIDs retain the existing canonical content
  contracts. The bundle validates their declared kinds before persistence, and
  typed resource validation runs again after generic envelopes are present.
  Event, fact, storyline, trigger, and context-note writes use a dependency-safe
  order so exact same-bundle evidence is fully typed before its consumer.
- `RevisionManager` owns one short transaction: it locks and verifies the
  canonical parent, batch-loads stable and exact reference targets, resolves
  replacement envelopes, retires prior versions, inserts every item/version,
  invokes typed persisters and projection builders, and advances the current
  pointer only after all validation succeeds.
- The resulting hash is computed from the pinned visible state plus the accepted
  writes before the immutable revision row is inserted. After typed rows and
  projections are flushed, all five resource readers independently reconstruct
  the visible state and must produce the same hash before pointer advancement.
- Empty bundles create no revision. Stale parents, wrong-kind local references,
  stale item revisions, duplicate context-note identities, typed validation
  failures, projection failures, and hash mismatches all leave revision history,
  typed content, search documents, retirements, and the current pointer
  unchanged.
- HTTP routes and reporter lifecycle integration remain deferred to
  `memory-12` through `memory-14`.

## `memory-11` Boundary Notes

- `MemoryRetrievalService` composes the competition-scoped search and typed
  managers. Every call supplies an exact pinned revision, and ranked candidates
  are returned only after their canonical version, item, kind, and competition
  identities agree with the projection.
- Results contain complete canonical typed aggregates plus score explanations
  and matched query values. Projection text, hashes, builder metadata, projected
  status/salience, search vectors, and ORM rows do not cross the boundary.
- Exact storyline evidence and fact originating events hydrate the referenced
  immutable version even after retirement. Stable related storylines and
  trigger targets resolve the target version visible at the pinned revision.
- Reference expansion is optional, typed, one hop, and returned as sidecars;
  canonical content is never rewritten or recursively enriched. Per-request
  caches reuse exact and revision-visible hydrations without persistent cache
  state.
- A projected candidate that cannot reconcile with canonical identity fails the
  complete request with `SearchProjectionHydrationError`. Missing canonical
  reference targets remain hard typed manager failures rather than partial
  results.
- HTTP schemas/routes, reporter tool integration, trigger scheduling,
  embeddings, and persistent hydration caches remain deferred.

## `memory-12` Boundary Notes

- The versioned HTTP boundary lives under
  `/api/v1/memory/competitions/{competition_id}`. It exposes current, exact,
  and historical canonical revision reads; exact-version and item-history reads
  for all five typed memory resources; and revision-pinned hydrated search.
- Each resource has distinct strict request and response schemas. `POST` creates
  a complete typed resource and `PUT /{item_id}` performs a complete replacement
  with an explicit expected item revision. Writes retain the application
  service's required generation provenance and expected canonical parent.
- A request-scoped dependency constructs one local-user `ManagerContext` from
  the competition path and optional `X-Correlation-ID`, then composes the typed
  managers, retrieval service, and mutation service over the process-owned
  session factory. Routes never receive a session or ORM row.
- Typed application failures map to stable HTTP status/code/message envelopes.
  Missing scoped resources return 404, canonical or item conflicts return 409,
  invalid reference semantics return 400, and canonical/projection integrity
  failures return safe 500 responses without storage details.
- Projection rebuild exposure, authentication/RBAC, reporter integration,
  trigger scheduling, embeddings, and persistent hydration caches remain
  deferred. FastAPI retains its standard 422 contract for transport validation.

## `memory-10` Boundary Notes

- `SearchDocumentManager.search()` requires an exact competition-scoped
  canonical revision and returns compact version candidates only. Canonical
  content and flattened document text never cross the manager boundary.
- Entity, evidence-version, related-item, tag, and PostgreSQL full-text signals
  combine with OR semantics. Kind, status, competition-season, and week filters
  combine with AND semantics; filter-only browsing remains supported.
- Ranking is a deterministic additive explanation: exact-overlap counts,
  PostgreSQL `ts_rank_cd`, and a `0.1 * salience` component are returned by
  name with stable match reasons and UUID tie-breaking.
- Rebuild locks the same competition current-pointer row used by canonical
  mutation, decodes every historical typed version through its retained-schema
  codec, and replaces all derived rows in one transaction. A failure preserves
  the prior projection, while a success leaves canonical revisions, hashes,
  typed content, and the pointer unchanged.
- Rebuild is exposed only as a manager operation in this layer. Typed hydration,
  HTTP/CLI exposure, reporter integration, trigger scheduling evaluation, and
  embeddings remain deferred.

## `memory-3` Boundary Notes

- The public revision boundary is deliberately read-only. The write skeleton is
  an unexported helper that locks and validates the canonical parent inside a
  caller-owned transaction; exposing a standalone public lock check would
  introduce a time-of-check/time-of-use race.
- This layer does not insert or advance revisions because the typed write bundle
  and canonical state-hash contract do not exist yet. Adding a public no-op
  commit or caller-supplied hash would create the wrong long-term interface.
- Historical visibility is a revision-package SQL composition primitive rather
  than a shallow public manager method. It resolves the pinned sequence from the
  exact scoped database revision and never trusts a constructible resource
  object's sequence value.
- Storyline entity/evidence/history behavior is proven with seeded PostgreSQL
  acceptance queries. Public storyline reads remain in `memory-6`.
- Future exact-evidence hydration must load the referenced immutable historical
  version even when it is no longer the visible version of its stable item.
- The real two-writer contention and rollback contract is deferred to
  `memory-9`, where one test can exercise the complete revision, typed-version,
  projection, hash, and pointer transaction. `memory-3` verifies scoped parent
  locking, sequence allocation, and typed stale-parent rejection only.

## Environment Notes

- A workspace `.venv` contains the locked development dependencies.
- Unit/backend tests use `.cache/tmp` as `TMP` and `TEMP` to avoid the host
  pytest temp-directory permission issue.
- PostgreSQL-backed tests use the repository's temporary PostgreSQL 17 Compose
  service and command-scoped `AIDAM_TEST_DATABASE_URL`. The `memory-11` run
  passed all 91 memory tests and all 163 backend tests.
- `uvx basedpyright backend` reports the same 16 diagnostics already present at
  the `memory-5` parent, including the existing Pydantic `schema_version`
  narrowing pattern. No new error originates in the `memory-11`
  implementation or tests.
