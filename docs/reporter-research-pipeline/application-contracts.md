# Reporter Research Pipeline Application Contracts

## Vocabulary and Ownership

- **Research brief:** runtime-owned typed state for verified research. Owned by the
  reporter runner for one run.
- **Brief projection:** deterministic Markdown rendering of the research brief at
  `research_brief.md`. Owned by the brief renderer.
- **Article artifact:** model-authored Markdown eligible for submission. Owned by
  the existing artifact store.
- **Source reference:** traceable description of the data or memory read that
  supports a fact. M1 preserves traceability; M2 may strengthen this into canonical
  receipt identifiers.
- **Readiness:** computed diagnostics indicating whether the current brief can
  support a defensible article. It is not procedure progress.
- **Curation packet/proposal bundle:** preliminary M2 input/output contracts. The
  memory finalizer, not the curator, owns persistent writes.

## M1 Public Contracts

The exact Python representation may use frozen dataclasses, Pydantic models, or the
repository's established schema mechanism, but it must preserve these semantics.

```text
BriefFact
  id: stable run-local identifier
  claim: non-empty factual statement
  category: non-empty string
  data_refs: one or more unique non-empty trace strings
  numbers: optional normalized mapping

BriefCallback
  id: stable run-local identifier
  current_fact_id: existing BriefFact identifier
  historical_fact_id: existing BriefFact identifier
  connection: non-empty explanation

BriefStoryline
  id: stable run-local identifier
  headline: non-empty string
  summary: non-empty string
  supporting_fact_ids: one or more existing BriefFact identifiers
  priority: bounded integer or enum
  tags: zero or more strings

BriefOutline
  sections: ordered sections with optional fact/storyline references

ResearchBrief
  facts, callbacks, storylines, outline, style, bias, readiness, revision
```

Model-facing tool capabilities are:

- `save_fact`
- `save_memory_callback`
- `save_storyline`
- `set_outline`
- `read_brief`

Names may be adjusted to local conventions, but handlers must remain specialized
typed operations. A generic `write_brief_markdown` capability is not equivalent.

The existing generic artifact capabilities remain available for article creation
and revision. They must reject the reserved `research_brief.md` path.

The model-facing persistent-memory capabilities are semantic:

- `search_memory`
- `save_memory_event`
- `upsert_storyline_memory_card`
- `save_storyline_trigger`
- `save_team_context`
- `save_league_note`

The create/replace proposal vocabulary remains an internal adapter contract and is
not registered with the model. Semantic tools use stable string IDs, team keys,
and narrative fields like the legacy reporter; the adapter resolves canonical
identity and expected revision internally.

After successful live submission, the bridge visits every final brief storyline
and buffers its existing supporting facts. It preserves brief claim, category,
numbers, and data references as source hints under a stable storyline/week/fact
key. Because brief data references are not typed receipt IDs, derived facts are
recorded as inferred rather than falsely marked source-backed. Missing support
IDs are skipped and unreferenced brief facts are not promoted.

## M1 Lifecycle and State Transitions

1. A run starts with a new empty `ResearchBrief` revision and no brief artifact.
2. Successful brief mutations increment the revision, recompute readiness and
   dependent staleness, render the projection, and emit research-log metadata.
3. Failed mutations leave the revision and projection unchanged.
4. The first successful mutation creates revision 1 of `research_brief.md`;
   `read_brief` at revision 0 does not materialize it.
5. Article artifacts may be created or revised at any brief revision.
6. Submission requires at least one verified fact, selects a non-empty article
   artifact, and captures the final brief revision/readiness in reporter output.
7. A run-scoped brief is immutable after reporter completion.
8. Live semantic memory mutations and bridged facts remain buffered until
   generation finalization.
9. Successful live finalization commits the complete bundle atomically; failed or
   cancelled runs discard it.
10. Backtest memory writes are read-only eval no-ops and the brief bridge is
    skipped, so canonical memory never advances.

Idempotent replay of the same normalized mutation returns the existing logical
item or a no-op result instead of adding a duplicate.

## M1 Invariants

- Every fact has at least one source reference.
- Every callback references two existing facts.
- Every storyline has at least one existing supporting fact.
- Every outline fact/storyline reference resolves within the current brief.
- Removing or materially replacing supporting state marks dependent state stale or
  requires it to be updated; stale dependencies cannot silently appear ready.
- The rendered projection is a deterministic function of the structured brief and
  revision.
- Generic artifact operations cannot create, mutate, submit, or shadow the brief
  projection.
- Style and bias are immutable values resolved from `ReportConfig`.
- Procedures do not gate brief, data, memory, artifact, or submission tools.
- Bias changes framing and emphasis only; it cannot alter factual brief state.
- The selected article remains the publishable output. The brief remains research
  evidence and is not selected as the article.
- Model-facing memory tools never expose create-versus-replace branching or ask
  the model to supply an optimistic revision number.
- Successful live submission bridges supporting facts for every final brief
  storyline and no unreferenced fact.

## M1 Error Semantics

Brief tool failures distinguish at least:

- invalid arguments;
- unknown or stale reference;
- duplicate/idempotent mutation;
- reserved artifact path; and
- projection/render failure.

Validation failures are model-correctable and remain within the agent loop.
Internal render/storage failures follow the runner's existing fatal tool-error
policy. Error payloads must be concise and must not expose secrets or raw internal
exceptions.

## Compatibility and Transition

- Reporter output exposes `research_brief.md` among observable
  artifacts, but its producer changes from the model-facing generic artifact store
  to the renderer.
- Historical generations that stored `research/brief.md` remain unchanged and
  readable through the generic artifact API; new runs use only the flat path.
- Article artifact selection, run persistence, streaming events, and generation
  API shapes remain compatible.
- Existing buffered and atomic memory finalization remains unchanged during M1;
  the model-facing vocabulary becomes semantic without introducing a curator.
- The legacy `reporter_v2` package is not part of the migration.
- The prompt-only baseline PR must merge before M1 so the brief implementation is
  evaluated under adaptive orchestration rather than fixed procedure sequencing.

## M1 Acceptance Coverage

Focused tests must cover:

- schema validation and stable/idempotent identifiers;
- fact, callback, storyline, and outline mutations plus config-owned style/bias;
- cross-reference rejection and dependent staleness;
- deterministic projection at every successful revision;
- atomic behavior when projection fails;
- rejection of generic artifact operations on `research_brief.md`;
- rejection of article submission before at least one verified fact exists;
- compatible reporter output and article selection;
- adaptive interleaving and backtracking without procedure gating;
- no empty seed-artifact create/read turns; and
- current memory finalization compatibility;
- semantic memory create and stable-ID update behavior;
- deterministic successful-submit fact bridging and stable-ID idempotency; and
- failed-run rollback and read-only backtests that leave canonical revision state
  unchanged.

The reporter output includes this nested observability shape:

```text
run_log_summary.brief
  revision
  projection_revision | null
  fact_count
  callback_count
  storyline_count
  outline_section_count
  stale_callback_ids[]
  stale_storyline_ids[]
  outline_stale
  readiness_warnings[]
  first_fact_turn | null
  first_storyline_turn | null
  first_draft_turn | null
  submission_turn | null
```

Revision-zero or aborted runs may have a null projection revision and null
milestone turns. Successful runs have a projection because the submission gate
requires a verified fact.

The live M1 gate uses representative weeks, report types, and supported models. It
records research depth, verified fact/storyline coverage, factual accuracy,
research-to-drafting interleaving, total turns, latency, and token usage against
the prompt-only baseline. M2 cannot begin until the results and an explicit go/no-go
decision are recorded.

## Preliminary M2 Contracts

These contracts establish the boundary but are not implementation-ready until the
deferred M2 decisions are resolved.

```text
MemoryCurationInput
  generation_id
  league_id and season scope
  final ResearchBrief
  selected article
  relevant pinned memory
  bounded evidence/receipt catalog

MemoryProposalBundle
  proposal identities
  typed storyline/fact/event/context mutations
  evidence references
  confidence and rationale metadata
```

The curator may return zero proposals. It may not execute memory writes. The
existing validator/finalizer owns authorization, referential integrity,
idempotency, and persistence. Curator failure never invalidates a successful
article.
