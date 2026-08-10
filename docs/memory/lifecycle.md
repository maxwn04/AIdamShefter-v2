# Memory Lifecycle

**Status:** Application pipeline design; database primitives implemented

## Live Article Generation

### 1. Resolve immutable inputs

Before the reporter runs, the generation service resolves and seals:

- one cutoff-safe Sleeper data snapshot;
- the competition's current canonical memory revision;
- domain and knowledge cutoffs;
- the generation manifest and reporter configuration.

The generation stores the exact input memory revision ID. No later memory change
can alter what this run was allowed to retrieve.

The generation service then creates one `GenerationMemoryContext` containing
the competition ID, generation ID, pinned canonical revision, retrieval
dependency, and an empty typed mutation buffer. This context is scoped to the
run and does not hold a database session.

### 2. Discover memory candidates

The reporter extracts teams, players, transactions, matchups, and themes from the
request and current factual snapshot. Its memory-search tool calls the
generation-scoped context, which delegates to the retrieval service using:

- pinned canonical revision visibility;
- competition scope;
- entity and trigger matches;
- lexical text;
- optional structured filters and vector similarity.

The projection was previously built when each candidate version was committed;
it is not regenerated for this article.

Every search remains grounded at the pinned canonical revision. Buffered
proposals from this generation are not included in retrieval and cannot become
research inputs for the run that proposed them.

### 3. Hydrate canonical memory

Search returns compact candidate IDs and score explanations. The retrieval
service dispatches selected candidates to the appropriate typed resource
manager, which hydrates `memory_versions` and the corresponding typed version
table. The retrieval service optionally expands exact evidence and stable
related items at the same pinned revision.

The agent receives complete typed memory as research leads, not flattened search
documents and not article-ready factual truth. It verifies remembered claims
against the generation's frozen Sleeper snapshot.

### 4. Generate article and propose memory changes

The reporter completes research, brief, drafting, and verification, then
produces an article. Calls such as `save_fact`, `save_memory_event`, or
`replace_storyline` append typed proposals to the generation context's in-memory
buffer; they do not write canonical memory immediately. Proposal-local IDs allow
later calls in the same generation to express same-bundle references.

After successful article submission, the generation service takes the completed
bundle from the context and calls the mutation service once. A failed or
abandoned generation discards the buffer. Model calls and external tool work
therefore finish before the canonical memory transaction begins.

### 5. Validate the mutation bundle

The mutation service:

1. parses each proposed content object into its Pydantic type;
2. verifies expected item versions;
3. batch-loads referenced item and version IDs;
4. validates target kind and competition scope;
5. validates event/trigger discriminators, roles, and evidence policy;
6. constructs deterministic resulting content and search documents.

Invalid proposals return actionable application errors. They do not rely on raw
database constraint failures for semantic feedback.

### 6. Commit one canonical revision

In one short transaction, the revision manager:

1. locks `current_revisions` for the competition;
2. requires it to equal the generation's pinned input revision;
3. allocates the next canonical sequence;
4. creates new stable items where required;
5. retires replaced visible versions;
6. inserts complete `memory_versions` and typed content rows;
7. inserts their lexical/entity search documents;
8. verifies the resulting-state hash;
9. advances the current pointer and lock version.

If no accepted memory change remains, the transaction creates no revision. If
canonical memory advanced after the generation started, the mutation fails
without producing a sibling state or partial projection.

### 7. Add optional embeddings

After commit, an asynchronous task may create missing embedding rows keyed by
the new version's exact ID, document builder, model, and content hash. Embedding
failure does not make canonical memory unavailable or block lexical retrieval.

## Example

At canonical revision 10, stable storyline item `S` has visible version 2:

```text
subject: Team Taco
origin evidence: Trade event version E1
support evidence: Fact version F3
```

A new payoff is accepted at revision 11. The transaction retires storyline
version 2 and inserts version 3:

```text
subject: Team Taco
origin evidence: Trade event version E1
support evidence: Fact version F3
payoff evidence: Matchup event version M1
```

It also inserts a search document for storyline version 3. Searches pinned to
revision 10 still find version 2; searches pinned to revision 11 find version 3.
The evidence versions remain exact and do not silently change when their stable
items receive later corrections.

## Evaluation Workspaces

Historical and rolling evaluations continue to use reporting-owned serialized
workspace artifacts rather than alternative canonical rows. A workspace begins
from one pinned canonical revision, evolves its own deterministic memory artifact,
and has no effect on `current_revisions` unless it qualifies for the existing
fast-forward promotion policy.

Workspace retrieval may build an ephemeral equivalent of the search projection
from its serialized memory state. It must not insert alternative-history content
into canonical search documents.

## Failure and Recovery

- Canonical transaction failure leaves neither a partial revision nor partial
  search documents.
- Missing embeddings degrade only vector recall.
- A damaged or stale search projection is rebuilt from canonical typed versions.
- A builder change rebuilds projections without changing memory history.
- A stale live generation must rerun from the now-current canonical revision.
- A failed or abandoned generation discards its uncommitted mutation buffer.
- Multiple proposal tool calls from one generation create at most one canonical
  revision.
- A generation never retrieves its buffered proposals as canonical memory.
- Exact generation search/tool logs remain in reporting for audit.
