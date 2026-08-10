# Typed Memory Implementation Status

## Current Phase

**Active layer:** `memory-2` complete; `memory-3` queued  
**Current branch:** `codex/memory-2-contracts`  
**Stack:** `main` ← `memory-0` ← `memory-1` ← `memory-2`  
**Publication:** Remote branches exist through `memory-2`; PR state is unverified
because GitHub CLI is not authenticated in the implementation environment.

This file is the coordination ledger for the typed-memory application stack.
The completed database stack remains tracked separately in
[`docs/database/status.md`](../database/status.md).

## Layer Ledger

| Layer | Branch | State | Owner | Verification | Commit / PR |
| --- | --- | --- | --- | --- | --- |
| `memory-0` implementation plan | `codex/memory-0-implementation-plan` | Complete | `root` | Documentation review | `45477b0`; PR unverified |
| `memory-1` ORM modules | `codex/memory-1-orm-modules` | Complete | `root` | Schema-preserving split already committed | `b7f758c`; PR unverified |
| `memory-2` contracts | `codex/memory-2-contracts` | Complete | `root` + `contracts_audit` | 29 focused contract tests; backend: 52 passed, 49 PostgreSQL tests skipped | Branch head; PR unverified |
| `memory-3` revisions | `codex/memory-3-revisions` | Queued | Unassigned | Not started | — |
| `memory-4` facts | `codex/memory-4-facts` | Pending | Unassigned | Not started | — |
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

## Open Design Decisions

1. **`memory-3` query-proof boundary.** The layer requires storyline entity and
   exact-evidence query proofs, but `RevisionManager` cannot contain kind-specific
   SQL and `StorylineManager` is scheduled for `memory-6`. Recommended default:
   prove the PostgreSQL query shapes with seeded acceptance tests in `memory-3`
   while keeping public storyline reads in `memory-6`.
2. **Canonical state hashing.** The deterministic serialization and algorithm
   for `MemoryRevision.state_content_hash` are not specified. Recommended
   default: keep `memory-3` limited to transaction locking and stale-writer
   scaffolding, then settle state hashing with the complete mutation bundle in
   `memory-9`; do not accept an opaque caller-computed hash.
3. **Search-document builder contract.** Per-kind builders begin in `memory-4`,
   while the search-document application resource is otherwise scheduled with
   `memory-10`. Its smallest stable result contract must be chosen before the
   first builder lands.
4. **Projection rebuild ownership.** The transition design leaves command/API
   ownership open. Resolve before `memory-10` without moving canonical mutation
   ownership into the projection manager.
5. **Integration-tail stack split.** Layers `memory-12` through `memory-14` may
   become a second stack based on `memory-11`, but only with explicit approval.

## Environment Notes

- A workspace `.venv` contains the locked development dependencies.
- Unit/backend tests use `.cache/tmp` as `TMP` and `TEMP` to avoid the host
  pytest temp-directory permission issue.
- PostgreSQL-backed tests require `AIDAM_TEST_DATABASE_URL`; no local test
  database is currently configured.
