# Typed Memory Implementation Status

## Current Phase

**Active layer:** `memory-3` complete; `memory-4` decision gate
**Current branch:** `codex/memory-3-revisions`
**Stack:** `main` ← `memory-0` ← `memory-1` ← `memory-2` ← `memory-3`
**Publication:** Remote branches exist through `memory-2`; `memory-3` is local
only. PR state is unverified because GitHub CLI is not authenticated in the
implementation environment.

This file is the coordination ledger for the typed-memory application stack.
The completed database stack remains tracked separately in
[`docs/database/status.md`](../database/status.md).

## Layer Ledger

| Layer | Branch | State | Owner | Verification | Commit / PR |
| --- | --- | --- | --- | --- | --- |
| `memory-0` implementation plan | `codex/memory-0-implementation-plan` | Complete | `root` | Documentation review | `45477b0`; PR unverified |
| `memory-1` ORM modules | `codex/memory-1-orm-modules` | Complete | `root` | Schema-preserving split already committed | `b7f758c`; PR unverified |
| `memory-2` contracts | `codex/memory-2-contracts` | Complete | `root` + `contracts_audit` | 29 focused contract tests; backend: 52 passed, 49 PostgreSQL tests skipped | Branch head; PR unverified |
| `memory-3` revisions | `codex/memory-3-revisions` | Complete | `root` + `contracts_audit` + reviewers | 3 focused PostgreSQL tests; backend: 104 passed; basedpyright: clean | Local branch head; PR not published |
| `memory-4` facts | `codex/memory-4-facts` | Decision gate | Unassigned | Hash and builder contracts required before implementation | — |
| `memory-5` events | `codex/memory-5-events` | Pending | Unassigned | Not started | — |
| `memory-6` storylines | `codex/memory-6-storylines` | Pending | Unassigned | Not started | — |
| `memory-7` triggers | `codex/memory-7-triggers` | Pending | Unassigned | Not started | — |
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
2. **Canonical state hashing.** The deterministic serialization and algorithm
   for `MemoryRevision.state_content_hash` are not specified. Recommended
   default for `memory-3`: limit this layer to transaction locking and
   stale-writer scaffolding and do not accept an opaque caller-computed hash.
   The hash contract must be settled before `memory-4`, because complete
   FactManager create/replace operations would insert the first new canonical
   revisions. Deferring all manager commits until `memory-9` would be a plan
   deviation and requires explicit approval.
3. **Search-document builder contract.** Per-kind builders begin in `memory-4`,
   while the search-document application resource is otherwise scheduled with
   `memory-10`. Its smallest stable result contract must be chosen before the
   first builder lands.
4. **Projection rebuild ownership.** The transition design leaves command/API
   ownership open. Resolve before `memory-10` without moving canonical mutation
   ownership into the projection manager.
5. **Integration-tail stack split.** Layers `memory-12` through `memory-14` may
   become a second stack based on `memory-11`, but only with explicit approval.

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
  service and command-scoped `AIDAM_TEST_DATABASE_URL`. The test container and
  its tmpfs data were removed after the 104-test backend run passed.
