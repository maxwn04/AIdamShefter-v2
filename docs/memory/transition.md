# Memory Redesign Implementation Map

**Status:** Database schema implemented in the current `gh stack`; application work pending

## Starting Point

The original in-flight database baseline had:

- linear `memory_revisions` and one `current_revisions` pointer;
- stable `memory_items` and versioned `memory_versions`;
- typed storyline, fact, event, trigger, and context-note version tables;
- generic canonical `version_entities` and `version_relationships`;
- full-text indexes distributed across typed version text.

The memory-layer commit in the current stack now preserves the revision model
while replacing the generic canonical graph with typed storage plus a derived
retrieval projection.

## Target Changes

### Preserve

- `memory_revisions` and `current_revisions`;
- `memory_items` and `memory_versions`;
- introduced/retired visibility;
- item-local revision numbering;
- context-note stable scope and key;
- exact fact/event reporting receipts;
- canonical mutation concurrency behavior.

### Modify

- add a content-schema version to immutable typed content;
- add Pydantic-backed subjects, evidence, thematic references, event payloads,
  and trigger conditions to their owning typed version tables;
- make manager methods accept complete kind-specific content objects;
- move target-kind, role, scope, and payload validation into the application
  mutation boundary;
- replace type-specific search paths with one search-document manager.

### Remove as canonical state

- `memory.version_entities`;
- `memory.version_relationships`.

They should not remain as a parallel authoritative write model. If temporarily
retained during implementation, they are derived compatibility projections and
must have a planned removal point.

### Add

- `memory.memory_search_documents`;
- deterministic per-kind search-document builders;
- full-text and flattened entity/reference indexes;
- later, `memory.memory_search_embeddings` and asynchronous embedding creation.

## Implementation Order

The database portion of steps 3, 5, and 7 is complete. The remaining application
work should proceed in this order:

1. **Settle resource contracts.** Define the Pydantic content and reference
   models, including exact-version versus stable-item semantics.
2. **Prove the critical queries in code.** Demonstrate active storylines by
   franchise, storyline evolution, and storylines supported by exact fact
   versions.
3. **Change typed storage.** Add the new typed fields and content-schema version
   while retaining the linear revision envelope.
4. **Implement complete mutation APIs.** Add transactional reference validation,
   full replacement, and typed errors.
5. **Add the search projection.** Build it synchronously for accepted canonical
   versions and provide a deterministic rebuild command/service operation.
6. **Switch reporter retrieval.** Search projection first, then hydrate canonical
   typed aggregates and exact evidence.
7. **Remove generic graph writes and tables.** Delete the old entity/relationship
   authority after equivalent behavior is covered.
8. **Add embeddings only after lexical/entity retrieval is measured.** Keep the
   vector layer independently rebuildable.

The repository's clean-replacement policy means no production legacy-data import
is required. The in-flight memory layer was amended in place and its descendants
were rebased with `gh stack`, so no forward compatibility migration is needed.

## Acceptance Queries

The redesign is not complete until these behaviors are straightforward and
historically safe:

1. Find active storylines involving a given franchise or player at revision `R`.
2. Return every version of a storyline in item-local order.
3. Find storylines supported by an exact fact version.
4. Hydrate the exact evidence and visible thematic references for a candidate.
5. Search event-specific terms without discarding structured trade/matchup data.
6. Prevent a generation pinned to `R` from retrieving content introduced at
   `R + 1`.
7. Rebuild search documents without changing canonical memory revisions.
8. Add a new event payload type without changing unrelated memory contracts.

## Required Test Layers

- Pydantic unit tests for each content and reference discriminator;
- manager tests for complete replacement and application error behavior;
- transaction tests for stale writers and atomic projection insertion;
- historical-visibility tests for exact revision pinning;
- search-builder golden tests and deterministic rebuild tests;
- retrieval tests for entity, evidence, full-text, and later vector candidates;
- hydration tests proving search documents are never returned as canonical
  memory;
- schema-evolution tests decoding every retained content-schema version.

## Remaining Application Decisions

- final role enums and reference cardinalities;
- which event payload types are required in the first implementation;
- projection rebuild command/API ownership;
- embedding provider, model, and retention policy;
