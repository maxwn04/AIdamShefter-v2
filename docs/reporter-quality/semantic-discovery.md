# Hybrid memory discovery

## Searchable units and visibility

One searchable unit is the complete existing search document for one canonical
memory version: event narrative, callback review question, storyline narrative,
context note, or current fact. Text is not truncated for an efficiency target.
Explicit text discovery can include superseded narrative versions introduced at
or before the pinned revision. Superseded facts are excluded. Automatic working
context, due callbacks, and standing context continue to use current versions.

Competition, frozen season catalog and reporting-week bounds, pinned revision,
explicit franchise, season, kind, status and period filters apply before every
ranking strategy. Callback franchise filtering inherits only its direct eligible
storyline or origin event at the pin. Stable franchise identity connects renames;
similarity cannot override an identity filter. Historical status describes the
matched version, never the current state of that item.

Temporal eligibility checks both the version's preserved origin season/week and
its introduction revision's reporting season/week. A Week 17 update to an arc
originating in Week 1 must not appear in Week 8 coverage merely because its
origin stays unchanged. This additional boundary applies to direct callback
parent filtering and selected inspection/expansions as well as discovery. An
older eligible version remains historical at a later pin; filtering out the
pin-current version never grants write access to an older version.

## Ranking and inspection

Structured, lexical and semantic strategies are independent relevance signals
over the same eligible units. Rank fusion combines their ordered results.
Semantic similarity must meet a relevance threshold; salience alone cannot turn
a semantic nonmatch into a result. Keep one strongest version per canonical item,
preferring the current version on ties, to avoid repeated versions of one arc
crowding out distinct events or questions. Exact selected versions retain full
detail and paginated history/evidence through `inspect_memory`.

Search cards identify current-at-pin versus superseded narrative provenance.
Historical matches and their inspection handles are read-only and cannot replace
current update targets in runtime caches. Similarity establishes relevance only;
it neither supports a factual assertion nor resolves a callback. Existing source
validation, advisory article verification and callback lifecycle remain intact.

## Derived embedding lifecycle

Embeddings live in an additive derived PostgreSQL table, separate from canonical
memory. The index identifies provider, model, dimensions, text-format version,
source builder version, source hash and exact input text hash. Rebuilding or
changing model identity cannot mutate canonical versions or frozen artifacts.
The initial provider configuration is `text-embedding-3-large`, 3072 dimensions.
Semantic capability is opt-in; an explicit indexing operation validates supplied
documents against canonical projections before making document embedding calls.
Search reads compatible stored embeddings and may embed its query; it does not
silently index documents or rewrite memory.

The semantic scorer receives only already eligible documents and never expands
their scope. Missing, stale, disabled or unavailable index/provider states are
reported separately from a successful search with no relevant result. Lexical and
structured discovery continue when semantic coverage is degraded. Index contents
are rebuildable; malformed vectors, wrong dimensions, nonfinite values and source
hash mismatches are ineligible. No separate vector service or search platform is
required for the current corpus size.

### Native exact vector search

Use maintained pgvector storage and database-side cosine distance instead of
loading embedding arrays into Python for custom similarity calculations. The
Python adapter is `pgvector.sqlalchemy.Vector`; compatible IDs and metadata are
checked without transferring stored vectors to the application. Native
`public.cosine_distance` evaluates only the eligible versions and matching
provider/model/dimension/content identity. Existing rank fusion still combines
structured, lexical and semantic signals and selects one version per item.

Search is exact over that eligible set. No HNSW or IVFFlat index is installed;
introduce approximate search only when measured retrieval needs justify its
recall/latency tradeoff. The variable-dimension vector column supports the current
3072-dimensional model alongside differently identified models. Zero vectors are
not usable cosine inputs and are reported stale. Native vector storage rejects
nonfinite values and the dimension constraint must match model metadata.

Migration 0014 converts the existing derived arrays into pgvector values without
regenerating embeddings or changing canonical memory. Values use native float32
precision; a downgrade restores arrays at that precision, not the original extra
float64 bits. Incompatible legacy values abort migration transactionally for
explicit derived-index repair. Downgrade leaves the shared extension installed.

The server must provide pgvector. Before migration, an administrator runs
`infra/database/bootstrap_extensions.sql` after role bootstrap to enable it in
`public`. An existing installation in another schema needs administrator review;
the application does not relocate shared extensions or gain superuser privileges.
The local compose image and initialization scripts supply this prerequisite.
Provision it on restore targets too: application-schema dumps exclude the public
extension. Semantic functions are schema-qualified, so hardened runtime and
migration search paths remain unchanged.

Prefer these maintained database primitives over custom vector infrastructure.
Structured/lexical discovery and the semantic opt-in default remain unchanged.
See [pgvector](https://github.com/pgvector/pgvector#querying) and its
[SQLAlchemy adapter](https://github.com/pgvector/pgvector-python#sqlalchemy).

### Operating the index

Apply the additive database migration before indexing. The indexing manifest is
a JSON object with `competition_id` and `documents`. Each document carries the
exact projection's `version_id`, `document_text`, `content_hash` and
`builder_version`; it is a derived input manifest, not a canonical memory write.
Select projection rows for the intended competition from
`memory.memory_search_documents`. Include older narrative versions when building
an index intended for historical discovery. The command checks every supplied
row against that competition's database projection before any provider call.

```sh
# AIDAM_DATABASE_URL selects the intended database. Preview performs no paid calls.
python -m backend.services.memory.semantic_index memory-index-manifest.json
# Explicit indexing uses OPENAI_API_KEY; repeat safely to fill missing/stale rows.
python -m backend.services.memory.semantic_index memory-index-manifest.json --execute
```

Enable query embeddings separately with `AIDAM_MEMORY_SEMANTIC_ENABLED=true`.
`AIDAM_MEMORY_EMBEDDING_MODEL`, `AIDAM_MEMORY_EMBEDDING_DIMENSIONS` and
`AIDAM_MEMORY_EMBEDDING_TIMEOUT_SECONDS` configure the provider identity and timeout.
The defaults are `text-embedding-3-large`, `3072`, and `30` seconds. Match the
index command's `--model` and `--dimensions` to those settings. A changed identity
does not reuse incompatible vectors: rebuild explicitly, then confirm `ready`
coverage in search results. Failed batches are retryable; already compatible
rows are reused. An absent index table or provider error leaves lexical and
structured retrieval available with degraded status.

Reciprocal-rank fusion uses an offset of 60 and an initial cosine relevance
floor of 0.35. The floor is not confidence in a claim. Quality review may change
it based on inspected relevant and irrelevant leads; deterministic vector tests
alone do not establish an appropriate threshold for every league or model.

## Ownership and acceptance

Index implementation owns the new embedding model/migration, shared semantic
contracts, provider, storage and explicit indexing command. Retrieval owns search
eligibility, rank fusion, candidate provenance and service propagation. The
coordinator owns reporter presentation, composition, durable docs and retained
corpus comparison. These surfaces are edited in isolated worktrees; independent
review covers each slice and their integration before publication.

Targeted checks cover pins, future and foreign versions, hard identity filters,
historical read protection, ranking/deduplication, missing/stale index states and
rebuild preservation. A small retrieval-only comparison keeps exact-name,
paraphrase, abstract narrative, rename, historical, distractor and unsupported
queries, including failures. Missing written memory is distinguished from a
retrieval miss. Retrieval outcomes do not establish changed article quality.
Paid embedding calls require approval of their exact scope and cost estimate;
merging, production adoption and paid reporter evaluations are separate decisions.
