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
- Existing direct memory proposal/finalization behavior remains unchanged during
  M1 so research quality can be evaluated without conflating a new curator.
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
- current memory finalization compatibility.

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
