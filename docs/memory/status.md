# Memory Service Implementation Status

## Current Phase

**Phase:** Application memory implementation
**Architecture:** Modular-monolith service with typed Python contracts
**Persistence:** Canonical PostgreSQL schema and search-document table implemented
**Compatibility:** Clean replacement; legacy `reporter_memory` persistence APIs
are not preserved

## Components

| Component | Status | Output |
| --- | --- | --- |
| Canonical revision and typed-version schema | Implemented | `../database/memory.md` |
| Typed content and reference design | Designed | `application-contracts.md` |
| Service boundaries and public contracts | Designed | `service-architecture.md` |
| Resource objects and schema converters | Implemented | `backend/resources/memory/objects.py` |
| Stable application errors | Implemented | `backend/resources/memory/errors.py` |
| Memory resource manager and canonical reads | Implemented | `backend/resources/memory/manager.py` |
| Complete-bundle mutation transaction | Pending | Generation-derived context plus `MemoryManager` transaction |
| Authoritative search-document builder | Implemented | `backend/resources/memory/search_documents.py` |
| Revision-pinned retrieval and hydration | Pending | `MemoryService.at_revision` plus internal retrieval pipeline |
| Service facade and consumer protocols | Pending | `backend/services/memory/` |
| Basic canonical viewing and item history | Pending | `MemoryInspector` capability on `MemoryService` |
| Search-index status and rebuild CLI | Pending | `MemorySearchIndexAdmin` consumer port on `MemoryService` |
| Evaluation-workspace promotion integration | Pending | Evaluation-workspace manager-owned cross-resource transaction |
| Reporter/generation adapters | Pending | Reporter service memory tools |
| UI-specific memory API | Deferred | Shape after initial memory UX is designed |
| Legacy `reporter_memory` removal | Pending | After behavior parity |
| Vector embeddings | Deferred | Add only after baseline retrieval measurement |
| Decision history | Current | `log.md` |

## Settled Baseline

- Canonical memory is one linear revision history per competition.
- Storyline, fact, event, trigger, and context-note versions own complete typed
  content.
- Exact evidence targets immutable version IDs; evolving relationships target
  stable item IDs.
- The public application boundary returns resource objects, never ORM rows or
  search documents.
- Generation-time reads use a capability-bound pinned reader.
- `MemoryService` creates the pinned reader; its methods delegate to the same
  internal retrieval pipeline with a fixed scope.
- The reporter proposes memory changes but cannot commit canonical state.
- A mutation bundle names its producing generation; the memory manager derives
  competition, cutoffs, season, and its one base-revision concurrency token.
- Empty, identical, already-applied, and retry mutation cases return stable
  no-op/existing results rather than creating revisions or avoidable errors.
- An ordinary mutation creates zero or one revision in one short manager-owned
  transaction.
- Search documents are derived, synchronously created for new versions, and
  independently rebuildable.
- Mutation and rebuild use one authoritative deterministic document builder
  registry based only on immutable version content.
- Inspector and search-index-admin contracts are narrow consumer ports on the
  service, not runtime authorization and not mandatory coordinator classes.
- Inspection is limited to viewing canonical items/revisions and item history;
  search-index administration is limited to derived-projection status and
  rebuild.
- Evaluation promotion is a fast-forward write owned by the evaluation service,
  not an inspection or search-projection operation.
- Remembered claims remain narrative leads and must be verified against the
  generation's frozen Sleeper snapshot.

## Implementation Sequence

| Slice | State | Completion signal |
| --- | --- | --- |
| 1. Contracts, errors, and schema converters | Complete | All initial typed payloads decode and validate with unit coverage |
| 2. Canonical reads and hydration manager | Complete | Revision-pinned item/version/history queries pass PostgreSQL tests |
| 3. Search-document builder | Complete | One dispatcher produces identical mutation/rebuild output for every kind |
| 4. Canonical mutation transaction | Not started | Atomic create/replace, no-op/retry, stale-writer, reference, and projection tests pass |
| 5. Pinned retrieval pipeline | Not started | Entity, evidence, related-item, lexical, and historical-leakage tests pass |
| 6. Basic viewing, promotion integration, reporter/generation, and rebuild CLI | Not started | Narrow capabilities work without UI-specific business logic |
| 7. Legacy removal | Not started | No active imports or writes depend on `reporter_memory` |

## Remaining Decisions

One non-blocking tuning decision remains:

- maximum default retrieval result and evidence-expansion limits.

These do not block implementation of the shared reference primitives, revision
objects, stable errors, content-schema conversion framework, or canonical read
manager.

## Explicitly Deferred

- canonical branches, merges, and sibling histories;
- a separately deployed memory microservice;
- a generic graph or generic CRUD repository;
- embeddings and approximate vector indexes;
- durable rebuild jobs, leases, and automatic resume;
- candidate-level access counters and generalized RAG telemetry;
- advanced inspection, diffing, analytics, bulk editing, and restoration;
- an operator or user-facing projection API before a concrete UI need;
- legacy SQLite import or dual-read/dual-write compatibility.

Deferred seams should not become placeholder tables or unused interfaces. Add a
decision-log entry before expanding the baseline.

## Next Milestone

Implement slice 4 canonical mutation with one generation-derived transaction,
including no-op, retry, concurrency, reference, and atomic projection coverage.
Then add the already-designed pinned retrieval service without public adapters.

## PR Stack Coordination

The application implementation is delivered as a `gh stack` series based on
`main@32b2d88`. Agents own only the paths assigned below. Shared-path changes are
integrated by `root` after the owning agent reports completion.

| Stack layer | Branch | Owner | State | Assigned paths |
| --- | --- | --- | --- | --- |
| 1. Design and resource contracts | `codex/memory-service-contracts` | `contracts_agent` | Complete | `docs/memory/`; `backend/resources/memory/objects.py`; `errors.py`; resource contract tests |
| 2. Canonical persistence and search documents | `codex/memory-service-persistence` | `persistence_agent` | Complete | `backend/resources/memory/manager.py`; `search_documents.py`; persistence/builder tests |
| 3. Canonical mutation | `codex/memory-service-mutations` | Unassigned | Pending | mutation methods and transaction tests; no public adapters |
| 4. Pinned retrieval and inspection | `codex/memory-service-retrieval` | `service_agent` | In progress | `backend/services/memory/`; retrieval/inspection tests |
| 5. Composition and adapters | `codex/memory-service-integration` | `root` | Pending | composition, reporter tools, minimal API/CLI adapters, legacy-path removal, integration tests |
| 6. Workspace promotion | `codex/memory-workspace-promotion` | Unassigned | Pending | reporting-owned promotion workflow and private memory command |

Coordination rules:

- A stack layer may be split or combined only with a new `log.md` decision.
- `objects.py` and `search_documents.py` are the sole authorities for typed
  content and deterministic search-document construction respectively.
- Agents do not add alternate repositories, per-kind service methods, or
  projection-specific builders.
- Status moves to `Complete` only after the layer's focused tests pass and root
  reviews the resulting diff.
- Promotion remains the final layer because it requires the reporting resource
  boundary; it must not leak sessions into public services.

## Verification Expectations

- Resource-contract tests use no database.
- Manager and mutation tests use real PostgreSQL; SQLite and mocked ORM sessions
  are not substitutes for revision and concurrency behavior.
- Search builders have deterministic golden tests.
- Retrieval tests prove that revision `R` cannot see versions introduced at
  `R + 1`.
- Adapter tests prove that ORM and search-document shapes do not cross the
  service boundary.
