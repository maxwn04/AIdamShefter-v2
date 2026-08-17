# Typed Memory Implementation Status

## Current Phase

**Active layer:** `memory-7` complete; `memory-8` is next
**Current branch:** `codex/memory-7-triggers`
**Stack:** `main` <- `memory-0` <- `memory-1` <- `memory-2` <- `memory-3` <- `memory-4` <- `memory-5` <- `memory-6` <- `memory-7`
**Publication:** Stack #108 is published through draft PR #112 (`memory-5`); `memory-6` and `memory-7` remain local.

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
| `memory-6` storylines | `codex/memory-6-storylines` | Complete | `root` | 7 focused storyline tests; memory: 56 passed; backend: 128 passed; basedpyright found no new errors and 16 pre-existing backend errors | Active branch head; not published |
| `memory-7` triggers | `codex/memory-7-triggers` | Complete | `root` | 8 focused trigger tests; memory: 64 passed; backend: 136 passed; basedpyright found no new errors and 16 pre-existing backend errors | Active branch head; not published |
| `memory-8` context notes | `codex/memory-8-context-notes` | Pending | Unassigned | Not started | — |
| `memory-9` mutation bundles | `codex/memory-9-mutation-bundles` | Pending | Unassigned | Not started | — |
| `memory-10` search projection | `codex/memory-10-search-projection` | Pending | Unassigned | Not started | — |
| `memory-11` retrieval | `codex/memory-11-retrieval` | Pending | Unassigned | Not started | — |
| `memory-12` HTTP API | `codex/memory-12-api` | Pending | Unassigned | Not started | — |
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
4. **Projection rebuild ownership.** The transition design leaves command/API
   ownership open. Resolve before `memory-10` without moving canonical mutation
   ownership into the projection manager.
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
  service and command-scoped `AIDAM_TEST_DATABASE_URL`. The `memory-7` run
  passed all 64 memory tests and all 136 backend tests; the test container and
  its tmpfs data were removed afterward.
- `uvx basedpyright backend` reports the same 16 diagnostics already present at
  the `memory-5` parent, including the existing Pydantic `schema_version`
  narrowing pattern. No new error originates in the `memory-7`
  implementation or tests.
