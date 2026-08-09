# Memory Retrieval Projection

**Status:** Search-document schema implemented; builders and retrieval service pending

## Purpose

Canonical memory kinds should remain different when they are authored and
modified, but retrieval needs one uniform candidate space. A persistent derived
table translates typed versions into searchable documents.

The projection behaves like a custom database index:

- it is built once for each new memory version;
- every later generation reuses it;
- it can be deleted and deterministically rebuilt from canonical versions;
- it is never sufficient to reconstruct full canonical content.

## `memory.memory_search_documents`

One row per exact immutable memory version:

- `version_id` primary key;
- item ID, competition ID, and memory kind;
- status, salience, season/week, and tags where applicable;
- flattened typed entity keys;
- exact evidence-version IDs;
- stable related-item IDs;
- deterministic document text;
- PostgreSQL `tsvector` search value;
- document-builder version and canonical content hash;
- indexed time.

Illustrative flattened values:

```text
entity_keys
  franchise:<uuid>
  player:<sleeper-player-id>
  roster:<uuid>

evidence_version_ids
  <fact-version-uuid>
  <event-version-uuid>

related_item_ids
  <storyline-item-uuid>
```

These may be stored as native text/UUID arrays with GIN indexes. They are derived
from richer Pydantic-backed canonical content and are not exposed as mutation
contracts.

Baseline indexes should support:

- competition, kind, and status filtering;
- item/version lookup;
- GIN containment on entity, evidence, related-item, and tag arrays;
- GIN full-text search on the document vector.

Exact indexes should be selected with representative `EXPLAIN` plans rather than
preemptively duplicating every field.

## Search-Document Building

Each canonical kind has a deterministic builder:

```python
build_storyline_document(content: StorylineContent) -> SearchDocument
build_fact_document(content: FactContent) -> SearchDocument
build_event_document(content: EventContent) -> SearchDocument
build_trigger_document(content: TriggerContent) -> SearchDocument
build_context_note_document(content: ContextNoteContent) -> SearchDocument
```

Builders flatten type-specific structure into a common shape and render useful
search text from:

- headline, summary, claim, narrative, and outlook;
- tags, event type, arc type, and status;
- participant display names and stable keys;
- concise evidence and relationship labels.

The initial lexical/entity document is inserted in the same canonical mutation
transaction as its source version. A successfully visible memory version is
therefore immediately searchable.

## Revision-Grounded Search

A generation pins canonical revision `R`. Candidate queries join search documents
to canonical version visibility and require:

```text
introduced_sequence <= R.sequence_number
and
(retired_sequence is null or retired_sequence > R.sequence_number)
```

The projection may later duplicate visibility sequences for performance, but
`memory_versions` and `memory_revisions` remain authoritative. Search must never
return a version introduced after the generation's pinned revision.

## Candidate Pipeline

Candidate discovery combines independent signals:

1. explicit trigger matches;
2. exact entity overlap;
3. exact evidence or related-item lookup;
4. PostgreSQL full-text search;
5. optional vector similarity;
6. status, salience, event fit, and light recency policy.

The system should retain named score components or use rank fusion rather than
pretending raw full-text and vector scores have the same scale.

Search returns compact leads:

```json
{
  "version_id": "...",
  "kind": "storyline",
  "score": 0.87,
  "matched_entities": ["franchise:..."],
  "match_reasons": ["entity_overlap", "lexical_match"]
}
```

The manager hydrates the highest-value leads from canonical typed tables and
returns the complete content and requested references to the agent.

## Vector Search

Embeddings are derived from search documents but stored separately:

### `memory.memory_search_embeddings`

- exact memory-version ID;
- embedding model and dimensions;
- document-builder version;
- document content hash;
- optional chunk number;
- vector and creation time.

The unique identity includes version, model, builder version, hash, and chunk so
the application can re-embed content without rewriting memory.

Embedding input should contain the owning typed content plus participant names
and concise relationship labels. It should not eagerly expand complete linked
facts and events unless dependency tracking is added; otherwise a linked-content
change would require finding and re-embedding every owner.

Embeddings may be generated asynchronously after the lexical projection commits.
Until then, entity, trigger, relationship, and full-text retrieval remain fully
available. Competition and pinned-revision filtering occurs before vector
candidates are accepted. Exact filtered vector scoring is preferred at expected
league scale; approximate indexes are added only after profiling.

## Rebuild and Caching

A projection rebuild:

1. scans canonical memory versions;
2. decodes each version through its content-schema converter;
3. invokes the current deterministic builder;
4. replaces projection rows;
5. queues embeddings whose model/builder/hash tuple is missing.

Rebuilding changes retrieval behavior, not canonical history, and therefore does
not create memory revisions.

Hydrated immutable typed versions may be cached by exact `version_id`. A pinned
revision determines which IDs are visible; the cached aggregate itself never
changes. Redis or a PostgreSQL materialized view is unnecessary until measured
load justifies another cache layer.
