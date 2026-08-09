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

### 2. Discover memory candidates

The reporter extracts teams, players, transactions, matchups, and themes from the
request and current factual snapshot. Its memory-search tool queries the existing
search projection using:

- pinned canonical revision visibility;
- competition scope;
- entity and trigger matches;
- lexical text;
- optional structured filters and vector similarity.

The projection was previously built when each candidate version was committed;
it is not regenerated for this article.

### 3. Hydrate canonical memory

Search returns compact candidate IDs and score explanations. The memory manager
hydrates selected candidates from `memory_versions` and the corresponding typed
version table. It optionally expands exact evidence and stable related items at
the same pinned revision.

The agent receives complete typed memory as research leads, not flattened search
documents and not article-ready factual truth. It verifies remembered claims
against the generation's frozen Sleeper snapshot.

### 4. Generate article and propose memory changes

The reporter completes research, brief, drafting, and verification, then produces
an article and an optional typed memory mutation bundle. Model calls and external
tool work finish before the canonical memory transaction begins.

### 5. Validate the mutation bundle

Application code:

1. parses each proposed content object into its Pydantic type;
2. loads competition, season, cutoffs, and the base revision from the producing
   generation rather than accepting caller-supplied copies;
3. validates same-bundle keys, references, and contradictions;
4. removes identical replacements and already-represented transitions;
5. batch-loads referenced item and version IDs;
6. validates persisted target kind and competition scope;
7. constructs search documents through the one authoritative builder registry.

Invalid proposals return actionable application errors. They do not rely on raw
database constraint failures for semantic feedback.

### 6. Commit one canonical revision

In one short transaction, the manager:

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
without producing a sibling state or partial projection. Retrying a generation
that already produced its revision returns that existing committed result.

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
- Exact generation search/tool logs remain in reporting for audit.
